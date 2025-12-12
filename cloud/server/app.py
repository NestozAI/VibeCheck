"""
VibeCheck Cloud Server
- Slack OAuth로 멀티 워크스페이스 지원
- Agent WebSocket 연결 관리
- 메시지 중계
- Block Kit UI + Interactivity
- Allowlist 관리
"""

import os
import json
import logging
import asyncio
from typing import Dict, List
from contextlib import asynccontextmanager
from urllib.parse import parse_qs

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
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

# API Key -> (team_id, channel, message_ts) 매핑 (응답 보낼 곳)
pending_responses: Dict[str, tuple] = {}

# API Key -> pending action data (file changes waiting for approval)
pending_actions: Dict[str, dict] = {}

# 기본 Allowlist (Claude Code 권한)
DEFAULT_ALLOWLIST = [
    "Bash(git status:*)",
    "Bash(git diff:*)",
    "Bash(git log:*)",
    "Bash(ls:*)",
    "Bash(cat:*)",
    "Bash(grep:*)",
    "Read",
    "Glob",
    "Grep",
]


# =============================================================================
# Block Kit 메시지 빌더
# =============================================================================

def build_processing_blocks() -> List[dict]:
    """처리 중 메시지 Block Kit"""
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "⏳ *처리 중...*"
            }
        }
    ]


def build_response_blocks(response_text: str, has_changes: bool = False, action_id: str = None) -> List[dict]:
    """응답 메시지 Block Kit"""
    blocks = []

    # 응답 텍스트 (최대 3000자로 제한)
    if len(response_text) > 3000:
        response_text = response_text[:2900] + "\n\n... (truncated)"

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": response_text
        }
    })

    # 파일 변경이 있으면 승인 버튼 추가
    if has_changes and action_id:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "actions",
            "block_id": f"approval_{action_id}",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ 반영하기", "emoji": True},
                    "style": "primary",
                    "action_id": "approve_changes",
                    "value": action_id
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ 취소", "emoji": True},
                    "style": "danger",
                    "action_id": "reject_changes",
                    "value": action_id
                }
            ]
        })

    return blocks


def build_status_blocks(status: str, message: str) -> List[dict]:
    """상태 메시지 Block Kit"""
    emoji = "✅" if status == "success" else "⚠️" if status == "warning" else "❌"
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{emoji} {message}"
            }
        }
    ]


def build_allowlist_blocks(allowlist: List[str], api_key: str) -> List[dict]:
    """Allowlist 관리 Block Kit"""
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🔐 권한 설정 (Allowlist)", "emoji": True}
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Claude Code가 자동으로 실행할 수 있는 명령어 목록입니다.\n권한을 추가하거나 제거하려면 아래 버튼을 사용하세요."
            }
        },
        {"type": "divider"}
    ]

    # 현재 allowlist 표시
    for i, item in enumerate(allowlist):
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"`{item}`"
            },
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "🗑️ 제거", "emoji": True},
                "style": "danger",
                "action_id": f"remove_allowlist_{i}",
                "value": item
            }
        })

    # 추가 버튼
    blocks.append({"type": "divider"})
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "➕ 권한 추가", "emoji": True},
                "action_id": "add_allowlist",
                "style": "primary"
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "🔄 기본값으로 초기화", "emoji": True},
                "action_id": "reset_allowlist"
            }
        ]
    })

    return blocks


def build_add_permission_modal(trigger_id: str) -> dict:
    """권한 추가 모달"""
    return {
        "type": "modal",
        "callback_id": "add_permission_modal",
        "title": {"type": "plain_text", "text": "권한 추가"},
        "submit": {"type": "plain_text", "text": "추가"},
        "close": {"type": "plain_text", "text": "취소"},
        "blocks": [
            {
                "type": "input",
                "block_id": "permission_input",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "permission_value",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "예: Bash(npm install:*)"
                    }
                },
                "label": {"type": "plain_text", "text": "권한 패턴"}
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "*예시:*\n• `Read` - 파일 읽기\n• `Edit` - 파일 수정\n• `Bash(npm:*)` - npm 명령어\n• `Bash(git commit:*)` - git commit"
                    }
                ]
            }
        ]
    }


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


# =============================================================================
# Slack Interactivity (버튼 클릭 등)
# =============================================================================

@app.post("/slack/interactions")
async def slack_interactions(request: Request):
    """Slack 인터랙션 처리 (버튼 클릭, 모달 제출 등)"""
    # Slack은 x-www-form-urlencoded로 payload를 보냄
    form_data = await request.form()
    payload_str = form_data.get("payload", "{}")
    payload = json.loads(payload_str)

    action_type = payload.get("type")
    logger.info(f"Interaction 수신: type={action_type}")

    if action_type == "block_actions":
        await handle_block_actions(payload)
    elif action_type == "view_submission":
        return await handle_view_submission(payload)

    return JSONResponse(content={})


async def handle_block_actions(payload: dict):
    """버튼 클릭 등 블록 액션 처리"""
    actions = payload.get("actions", [])
    user_id = payload.get("user", {}).get("id")
    team_id = payload.get("team", {}).get("id")
    channel_id = payload.get("channel", {}).get("id")
    trigger_id = payload.get("trigger_id")

    client = get_slack_client(team_id)
    if not client:
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(
            User.slack_user_id == user_id,
            User.slack_team_id == team_id
        ).first()

        if not user:
            return

        for action in actions:
            action_id = action.get("action_id", "")
            value = action.get("value", "")

            # 권한 추가 버튼
            if action_id == "add_allowlist":
                modal = build_add_permission_modal(trigger_id)
                await client.views_open(trigger_id=trigger_id, view=modal)

            # 권한 제거 버튼
            elif action_id.startswith("remove_allowlist_"):
                allowlist = json.loads(user.allowlist) if user.allowlist else DEFAULT_ALLOWLIST.copy()
                if value in allowlist:
                    allowlist.remove(value)
                    user.allowlist = json.dumps(allowlist)
                    db.commit()

                # 업데이트된 목록 표시
                await client.chat_postMessage(
                    channel=channel_id,
                    text="권한이 제거되었습니다.",
                    blocks=build_allowlist_blocks(allowlist, user.api_key)
                )

            # Allowlist 초기화
            elif action_id == "reset_allowlist":
                user.allowlist = json.dumps(DEFAULT_ALLOWLIST)
                db.commit()

                await client.chat_postMessage(
                    channel=channel_id,
                    text="권한이 초기화되었습니다.",
                    blocks=build_allowlist_blocks(DEFAULT_ALLOWLIST, user.api_key)
                )

            # 변경사항 승인
            elif action_id == "approve_changes":
                pending = pending_actions.get(value)
                if pending:
                    # Agent에게 승인 메시지 전송
                    ws = connected_agents.get(user.api_key)
                    if ws:
                        await ws.send_json({
                            "type": "approval",
                            "action_id": value,
                            "approved": True
                        })
                    del pending_actions[value]

                await client.chat_postMessage(
                    channel=channel_id,
                    text="변경사항이 승인되었습니다.",
                    blocks=build_status_blocks("success", "변경사항이 적용되었습니다.")
                )

            # 변경사항 거절
            elif action_id == "reject_changes":
                pending = pending_actions.get(value)
                if pending:
                    ws = connected_agents.get(user.api_key)
                    if ws:
                        await ws.send_json({
                            "type": "approval",
                            "action_id": value,
                            "approved": False
                        })
                    del pending_actions[value]

                await client.chat_postMessage(
                    channel=channel_id,
                    text="변경사항이 취소되었습니다.",
                    blocks=build_status_blocks("warning", "변경사항이 취소되었습니다.")
                )

    finally:
        db.close()


async def handle_view_submission(payload: dict) -> JSONResponse:
    """모달 제출 처리"""
    callback_id = payload.get("view", {}).get("callback_id")
    user_id = payload.get("user", {}).get("id")
    team_id = payload.get("team", {}).get("id")

    if callback_id == "add_permission_modal":
        # 권한 추가 모달 처리
        values = payload.get("view", {}).get("state", {}).get("values", {})
        permission_value = values.get("permission_input", {}).get("permission_value", {}).get("value", "")

        if permission_value:
            db = SessionLocal()
            try:
                user = db.query(User).filter(
                    User.slack_user_id == user_id,
                    User.slack_team_id == team_id
                ).first()

                if user:
                    allowlist = json.loads(user.allowlist) if user.allowlist else DEFAULT_ALLOWLIST.copy()
                    if permission_value not in allowlist:
                        allowlist.append(permission_value)
                        user.allowlist = json.dumps(allowlist)
                        db.commit()

                    # 업데이트된 목록 DM으로 전송
                    client = get_slack_client(team_id)
                    if client and user.slack_channel_id:
                        await client.chat_postMessage(
                            channel=user.slack_channel_id,
                            text=f"권한이 추가되었습니다: {permission_value}",
                            blocks=build_allowlist_blocks(allowlist, user.api_key)
                        )

            finally:
                db.close()

    return JSONResponse(content={})


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

            # Block Kit으로 환영 메시지
            welcome_blocks = [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "🎉 환영합니다!", "emoji": True}
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"API Key가 발급되었습니다:\n`{user.api_key}`"
                    }
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*서버에서 Agent를 실행해주세요:*"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"```git clone https://github.com/NestozAI/VibeCheck.git\ncd VibeCheck/cloud/agent\npip install -r requirements.txt\npython agent.py --key={user.api_key}```"
                    }
                },
                {"type": "divider"},
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "💡 `/permissions` 를 입력하면 Claude Code 권한을 관리할 수 있습니다."
                        }
                    ]
                }
            ]

            await client.chat_postMessage(
                channel=channel,
                text="환영합니다! API Key가 발급되었습니다.",
                blocks=welcome_blocks
            )
            return

        # 권한 관리 명령어 처리
        if message.lower() in ["/permissions", "/권한", "/allowlist"]:
            allowlist = json.loads(user.allowlist) if user.allowlist else DEFAULT_ALLOWLIST.copy()
            await client.chat_postMessage(
                channel=channel,
                text="권한 설정",
                blocks=build_allowlist_blocks(allowlist, user.api_key)
            )
            return

        # Agent 연결 확인
        if user.api_key not in connected_agents:
            not_connected_blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "⚠️ *Agent가 연결되지 않았습니다.*"
                    }
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"서버에서 Agent를 실행해주세요:\n```python agent.py --key={user.api_key}```"
                    }
                }
            ]
            await client.chat_postMessage(
                channel=channel,
                text="Agent가 연결되지 않았습니다.",
                blocks=not_connected_blocks
            )
            return

        # 사용량 체크
        if user.usage_count >= user.usage_limit:
            await client.chat_postMessage(
                channel=channel,
                text="사용량 한도에 도달했습니다.",
                blocks=build_status_blocks("error", "사용량 한도에 도달했습니다. 업그레이드가 필요합니다.")
            )
            return

        # 처리 중 메시지 (Block Kit)
        processing_msg = await client.chat_postMessage(
            channel=channel,
            text="처리 중...",
            blocks=build_processing_blocks()
        )
        message_ts = processing_msg.get("ts")

        # 응답 대기 정보 저장 (message_ts 포함)
        pending_responses[user.api_key] = (team_id, channel, message_ts)

        # Agent로 메시지 전송
        success = await send_to_agent(user.api_key, message)
        if not success:
            await client.chat_update(
                channel=channel,
                ts=message_ts,
                text="Agent 연결이 끊어졌습니다.",
                blocks=build_status_blocks("error", "Agent 연결이 끊어졌습니다. 다시 연결해주세요.")
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
                        team_id, channel, message_ts = pending
                        client = get_slack_client(team_id)
                        if client:
                            # Block Kit으로 응답 전송 (처리 중 메시지 업데이트)
                            response_blocks = build_response_blocks(response_text)
                            await client.chat_update(
                                channel=channel,
                                ts=message_ts,
                                text=response_text[:500],
                                blocks=response_blocks
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
