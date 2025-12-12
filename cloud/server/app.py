"""
VibeCheck Cloud Server
- Slack OAuth로 멀티 워크스페이스 지원
- Agent WebSocket 연결 관리
- 메시지 중계
"""

import os
import logging
import asyncio
from typing import Dict
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from dotenv import load_dotenv
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.oauth import AuthorizeUrlGenerator
from slack_sdk.oauth.installation_store import Installation
import httpx

from models import init_db, User, Workspace, SessionLocal

# 환경변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# 환경변수
# =============================================================================

SLACK_CLIENT_ID = os.environ.get("SLACK_CLIENT_ID")
SLACK_CLIENT_SECRET = os.environ.get("SLACK_CLIENT_SECRET")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080")

# OAuth scopes
SCOPES = [
    "chat:write",
    "im:history",
    "im:read",
    "im:write",
    "users:read",
]

# =============================================================================
# 연결 관리
# =============================================================================

# API Key -> WebSocket 매핑
connected_agents: Dict[str, WebSocket] = {}

# API Key -> (team_id, channel) 매핑 (응답 보낼 곳)
pending_responses: Dict[str, tuple] = {}


def get_slack_client(team_id: str) -> AsyncWebClient:
    """워크스페이스별 Slack 클라이언트 가져오기"""
    db = SessionLocal()
    try:
        workspace = db.query(Workspace).filter(Workspace.team_id == team_id).first()
        if workspace:
            return AsyncWebClient(token=workspace.bot_token)
        return None
    finally:
        db.close()


async def send_to_agent(api_key: str, message: str) -> bool:
    """Agent로 메시지 전송"""
    ws = connected_agents.get(api_key)
    if ws:
        try:
            await ws.send_json({
                "type": "query",
                "message": message
            })
            return True
        except Exception as e:
            logger.error(f"Agent 전송 실패: {e}")
            return False
    return False


# =============================================================================
# FastAPI App
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 실행"""
    init_db()
    logger.info("DB 초기화 완료")
    yield
    logger.info("서버 종료")


app = FastAPI(title="VibeCheck Cloud", lifespan=lifespan)


# =============================================================================
# 메인 페이지
# =============================================================================

@app.get("/")
async def root():
    """메인 페이지"""
    install_url = f"/slack/install"
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>VibeCheck</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 600px;
                margin: 100px auto;
                padding: 20px;
                text-align: center;
            }}
            h1 {{ color: #1a1a1a; }}
            p {{ color: #666; line-height: 1.6; }}
            .btn {{
                display: inline-block;
                background: #4A154B;
                color: white;
                padding: 12px 24px;
                border-radius: 8px;
                text-decoration: none;
                margin-top: 20px;
                font-weight: 500;
            }}
            .btn:hover {{ background: #611f69; }}
        </style>
    </head>
    <body>
        <h1>VibeCheck</h1>
        <p>Slack에서 서버를 원격으로 제어하세요.<br>
        Claude Code를 Slack DM으로 사용할 수 있습니다.</p>
        <a href="{install_url}" class="btn">Add to Slack</a>
    </body>
    </html>
    """)


@app.get("/health")
async def health():
    """헬스 체크"""
    return {
        "status": "ok",
        "connected_agents": len(connected_agents)
    }


# =============================================================================
# Slack OAuth
# =============================================================================

@app.get("/slack/install")
async def slack_install():
    """Slack 설치 시작"""
    if not SLACK_CLIENT_ID:
        return HTMLResponse("<h1>Error: SLACK_CLIENT_ID not configured</h1>")

    authorize_url = (
        f"https://slack.com/oauth/v2/authorize?"
        f"client_id={SLACK_CLIENT_ID}&"
        f"scope={','.join(SCOPES)}&"
        f"redirect_uri={BASE_URL}/slack/oauth/callback"
    )
    return RedirectResponse(authorize_url)


@app.get("/slack/oauth/callback")
async def slack_oauth_callback(code: str = None, error: str = None):
    """OAuth 콜백 처리"""
    if error:
        return HTMLResponse(f"<h1>Error: {error}</h1>")

    if not code:
        return HTMLResponse("<h1>Error: No code provided</h1>")

    # 토큰 교환
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": SLACK_CLIENT_ID,
                "client_secret": SLACK_CLIENT_SECRET,
                "code": code,
                "redirect_uri": f"{BASE_URL}/slack/oauth/callback"
            }
        )
        data = response.json()

    if not data.get("ok"):
        logger.error(f"OAuth 실패: {data}")
        return HTMLResponse(f"<h1>OAuth 실패: {data.get('error')}</h1>")

    # 워크스페이스 정보 저장
    team_id = data["team"]["id"]
    team_name = data["team"]["name"]
    bot_token = data["access_token"]
    bot_user_id = data.get("bot_user_id")
    installer_user_id = data.get("authed_user", {}).get("id")

    db = SessionLocal()
    try:
        workspace = db.query(Workspace).filter(Workspace.team_id == team_id).first()

        if workspace:
            # 기존 워크스페이스 업데이트
            workspace.bot_token = bot_token
            workspace.bot_user_id = bot_user_id
            workspace.team_name = team_name
        else:
            # 새 워크스페이스 생성
            workspace = Workspace(
                team_id=team_id,
                team_name=team_name,
                bot_token=bot_token,
                bot_user_id=bot_user_id,
                installer_user_id=installer_user_id
            )
            db.add(workspace)

        db.commit()
        logger.info(f"워크스페이스 설치됨: {team_name} ({team_id})")

    finally:
        db.close()

    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>설치 완료!</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 600px;
                margin: 100px auto;
                padding: 20px;
                text-align: center;
            }}
            h1 {{ color: #2eb67d; }}
            p {{ color: #666; }}
            code {{
                background: #f4f4f4;
                padding: 2px 8px;
                border-radius: 4px;
            }}
        </style>
    </head>
    <body>
        <h1>설치 완료!</h1>
        <p><strong>{team_name}</strong> 워크스페이스에 VibeCheck이 설치되었습니다.</p>
        <p>Slack에서 VibeCheck 봇에게 DM을 보내면 API Key가 발급됩니다.</p>
    </body>
    </html>
    """)


# =============================================================================
# Slack Events (HTTP 방식)
# =============================================================================

@app.post("/slack/events")
async def slack_events(request: Request):
    """Slack 이벤트 수신"""
    body = await request.json()

    # URL 검증 (Slack 앱 설정 시 필요)
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge")}

    # 이벤트 처리
    event = body.get("event", {})
    event_type = event.get("type")

    if event_type == "message":
        await handle_message_event(body, event)

    return {"ok": True}


async def handle_message_event(body: dict, event: dict):
    """메시지 이벤트 처리"""
    # 봇 메시지 무시
    if event.get("bot_id") or event.get("subtype"):
        return

    # DM만 처리
    if event.get("channel_type") != "im":
        return

    team_id = body.get("team_id")
    user_id = event.get("user")
    message = event.get("text", "").strip()
    channel = event.get("channel")

    if not message:
        return

    logger.info(f"메시지 수신: team={team_id}, user={user_id}, msg={message[:50]}")

    # Slack 클라이언트 가져오기
    client = get_slack_client(team_id)
    if not client:
        logger.error(f"워크스페이스를 찾을 수 없음: {team_id}")
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(
            User.slack_user_id == user_id,
            User.slack_team_id == team_id
        ).first()

        if not user:
            # 새 유저 생성
            user = User(
                slack_user_id=user_id,
                slack_team_id=team_id,
                slack_channel_id=channel
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            await client.chat_postMessage(
                channel=channel,
                text=f"환영합니다! API Key가 발급되었습니다.\n\n"
                     f"`{user.api_key}`\n\n"
                     f"서버에서 Agent를 실행해주세요:\n"
                     f"```\ngit clone https://github.com/NestozAI/VibeCheck.git\n"
                     f"cd VibeCheck/cloud/agent\n"
                     f"pip install -r requirements.txt\n"
                     f"python agent.py --key={user.api_key}\n```"
            )
            return

        # Agent 연결 확인
        if user.api_key not in connected_agents:
            await client.chat_postMessage(
                channel=channel,
                text=f"Agent가 연결되지 않았습니다.\n\n"
                     f"서버에서 Agent를 실행해주세요:\n"
                     f"```\ngit clone https://github.com/NestozAI/VibeCheck.git\n"
                     f"cd VibeCheck/cloud/agent\n"
                     f"pip install -r requirements.txt\n"
                     f"python agent.py --key={user.api_key}\n```"
            )
            return

        # 사용량 체크
        if user.usage_count >= user.usage_limit:
            await client.chat_postMessage(
                channel=channel,
                text="사용량 한도에 도달했습니다. 업그레이드가 필요합니다."
            )
            return

        # 응답 대기 정보 저장
        pending_responses[user.api_key] = (team_id, channel)

        # 처리 중 메시지
        await client.chat_postMessage(channel=channel, text="⏳ 처리 중...")

        # Agent로 메시지 전송
        success = await send_to_agent(user.api_key, message)
        if not success:
            await client.chat_postMessage(
                channel=channel,
                text="Agent 연결이 끊어졌습니다. 다시 연결해주세요."
            )
            return

        # 사용량 증가
        user.usage_count += 1
        db.commit()

    finally:
        db.close()


# =============================================================================
# Agent WebSocket
# =============================================================================

@app.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket, key: str):
    """Agent WebSocket 연결"""
    await websocket.accept()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.api_key == key).first()
        if not user:
            await websocket.send_json({"type": "error", "message": "Invalid API Key"})
            await websocket.close()
            return

        # 연결 등록
        connected_agents[key] = websocket
        user.agent_connected = True
        db.commit()

        logger.info(f"Agent 연결됨: {key[:20]}...")

        await websocket.send_json({
            "type": "connected",
            "message": "Successfully connected to VibeCheck Cloud"
        })

        # 메시지 수신 대기
        while True:
            try:
                data = await websocket.receive_json()

                if data.get("type") == "response":
                    # Agent 응답 -> Slack으로 전달
                    response_text = data.get("result", "")
                    pending = pending_responses.get(key)

                    if pending and response_text:
                        team_id, channel = pending
                        client = get_slack_client(team_id)
                        if client:
                            await client.chat_postMessage(
                                channel=channel,
                                text=response_text
                            )
                            logger.info(f"Slack으로 응답 전송: {response_text[:50]}...")

                elif data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})

            except WebSocketDisconnect:
                break

    except Exception as e:
        logger.error(f"WebSocket 오류: {e}")

    finally:
        if key in connected_agents:
            del connected_agents[key]

        user = db.query(User).filter(User.api_key == key).first()
        if user:
            user.agent_connected = False
            db.commit()

        db.close()
        logger.info(f"Agent 연결 해제: {key[:20]}...")


# =============================================================================
# 메인
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
