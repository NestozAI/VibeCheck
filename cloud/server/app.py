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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Form, Cookie, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import secrets
from datetime import datetime, timedelta
from dotenv import load_dotenv
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.oauth import AuthorizeUrlGenerator
from slack_sdk.oauth.installation_store import Installation
import httpx

from models import init_db, User, Workspace, Session, Message, SessionLocal

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
        <title>VibeCheck - Slack에서 Claude Code 원격 제어</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #0a0a0a;
                color: #e0e0e0;
                line-height: 1.6;
            }}
            .container {{
                max-width: 1000px;
                margin: 0 auto;
                padding: 0 24px;
            }}

            /* Hero Section */
            .hero {{
                text-align: center;
                padding: 80px 0 60px;
                position: relative;
            }}
            .hero::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 50%;
                transform: translateX(-50%);
                width: 600px;
                height: 400px;
                background: radial-gradient(ellipse, rgba(0,255,0,0.1) 0%, transparent 70%);
                pointer-events: none;
            }}
            .logo-img {{
                width: 120px;
                height: 120px;
                margin-bottom: 24px;
                filter: drop-shadow(0 0 20px rgba(0,255,0,0.5));
            }}
            .logo {{
                font-size: 3.5rem;
                font-weight: 800;
                color: #00ff00;
                text-shadow: 0 0 30px rgba(0,255,0,0.5);
                margin-bottom: 24px;
            }}
            .tagline {{
                font-size: 1.5rem;
                color: #888;
                margin-bottom: 16px;
            }}
            .tagline strong {{
                color: #00ff00;
            }}
            .description {{
                font-size: 1.1rem;
                color: #666;
                max-width: 600px;
                margin: 0 auto 32px;
            }}
            .btn {{
                display: inline-block;
                background: #00ff00;
                color: #0a0a0a;
                padding: 16px 40px;
                border-radius: 8px;
                text-decoration: none;
                font-weight: 700;
                font-size: 1.1rem;
                transition: all 0.2s;
                box-shadow: 0 0 20px rgba(0,255,0,0.3);
            }}
            .btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 0 40px rgba(0,255,0,0.5);
            }}

            /* Demo Section */
            .demo {{
                padding: 60px 0;
            }}
            .demo h2 {{
                text-align: center;
                font-size: 2rem;
                margin-bottom: 40px;
                color: #fff;
            }}
            .demo-images {{
                display: flex;
                flex-direction: column;
                gap: 40px;
                align-items: center;
            }}
            .demo-img-wrapper {{
                position: relative;
                max-width: 900px;
                width: 100%;
            }}
            .demo-img-wrapper img {{
                width: 100%;
                border-radius: 12px;
                border: 1px solid #222;
                box-shadow: 0 0 40px rgba(0,255,0,0.1);
            }}
            .demo-img-caption {{
                text-align: center;
                color: #888;
                font-size: 0.95rem;
                margin-top: 16px;
            }}

            /* How it works */
            .how {{
                padding: 60px 0;
                background: #0d0d0d;
            }}
            .how h2 {{
                text-align: center;
                font-size: 2rem;
                margin-bottom: 48px;
                color: #fff;
            }}
            .steps {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 32px;
            }}
            .step {{
                text-align: center;
                padding: 24px;
            }}
            .step-num {{
                width: 48px;
                height: 48px;
                background: linear-gradient(135deg, #00ff00, #00aa00);
                color: #0a0a0a;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: 700;
                font-size: 1.2rem;
                margin: 0 auto 16px;
            }}
            .step h3 {{
                color: #fff;
                margin-bottom: 8px;
            }}
            .step p {{
                color: #666;
                font-size: 0.95rem;
            }}
            .step code {{
                background: #1a1a1a;
                padding: 2px 8px;
                border-radius: 4px;
                font-size: 0.85rem;
                color: #00ff00;
            }}

            /* Pricing */
            .pricing {{
                padding: 60px 0;
            }}
            .pricing h2 {{
                text-align: center;
                font-size: 2rem;
                margin-bottom: 48px;
                color: #fff;
            }}
            .plans {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 24px;
                max-width: 700px;
                margin: 0 auto;
            }}
            .plan {{
                background: #111;
                border: 1px solid #222;
                border-radius: 16px;
                padding: 32px;
            }}
            .plan.pro {{
                border-color: #00ff00;
                box-shadow: 0 0 30px rgba(0,255,0,0.1);
                position: relative;
            }}
            .plan.pro::before {{
                content: 'RECOMMENDED';
                position: absolute;
                top: -12px;
                left: 50%;
                transform: translateX(-50%);
                background: #00ff00;
                color: #0a0a0a;
                padding: 4px 16px;
                border-radius: 20px;
                font-size: 0.75rem;
                font-weight: 700;
            }}
            .plan h3 {{
                color: #fff;
                font-size: 1.5rem;
                margin-bottom: 8px;
            }}
            .plan .price {{
                font-size: 2.5rem;
                font-weight: 700;
                color: #00ff00;
                margin: 16px 0;
            }}
            .plan .price span {{
                font-size: 1rem;
                color: #666;
                font-weight: normal;
            }}
            .plan ul {{
                list-style: none;
                margin: 24px 0;
                text-align: left;
            }}
            .plan li {{
                padding: 8px 0;
                color: #888;
            }}
            .plan li::before {{
                content: '✓';
                color: #00ff00;
                font-weight: bold;
                margin-right: 8px;
            }}
            .plan .btn {{
                width: 100%;
                text-align: center;
            }}
            .btn-free {{
                background: #222;
                color: #888;
                box-shadow: none;
            }}
            .btn-free:hover {{
                background: #333;
            }}

            /* Footer */
            footer {{
                padding: 40px 0;
                text-align: center;
                color: #444;
                border-top: 1px solid #1a1a1a;
            }}

            /* Responsive */
            @media (max-width: 768px) {{
                .steps {{
                    grid-template-columns: 1fr;
                }}
                .plans {{
                    grid-template-columns: 1fr;
                }}
                .logo {{
                    font-size: 2.5rem;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <section class="hero">
                <!-- Logo SVG -->
                <svg class="logo-img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
                    <defs>
                        <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
                            <feGaussianBlur stdDeviation="6" result="coloredBlur"/>
                            <feMerge>
                                <feMergeNode in="coloredBlur"/>
                                <feMergeNode in="SourceGraphic"/>
                            </feMerge>
                        </filter>
                        <filter id="strongGlow" x="-100%" y="-100%" width="300%" height="300%">
                            <feGaussianBlur stdDeviation="12" result="coloredBlur"/>
                            <feMerge>
                                <feMergeNode in="coloredBlur"/>
                                <feMergeNode in="coloredBlur"/>
                                <feMergeNode in="SourceGraphic"/>
                            </feMerge>
                        </filter>
                    </defs>
                    <rect x="0" y="0" width="512" height="512" rx="80" ry="80" fill="#0a0a0a"/>
                    <g stroke="#1a1a1a" stroke-width="1">
                        <line x1="0" y1="128" x2="512" y2="128"/>
                        <line x1="0" y1="256" x2="512" y2="256"/>
                        <line x1="0" y1="384" x2="512" y2="384"/>
                        <line x1="128" y1="0" x2="128" y2="512"/>
                        <line x1="256" y1="0" x2="256" y2="512"/>
                        <line x1="384" y1="0" x2="384" y2="512"/>
                    </g>
                    <path d="M 40 280 L 120 280 L 160 280 L 200 320 L 256 140 L 310 320 L 350 280 L 400 280 L 472 280"
                        fill="none" stroke="#00ff00" stroke-width="8" stroke-linecap="round" stroke-linejoin="round" filter="url(#strongGlow)"/>
                    <path d="M 40 280 L 120 280 L 160 280 L 200 320 L 256 140 L 310 320 L 350 280 L 400 280 L 472 280"
                        fill="none" stroke="#00ff00" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" opacity="0.5"/>
                    <path d="M 380 400 L 405 430 L 460 360"
                        fill="none" stroke="#00ff00" stroke-width="6" stroke-linecap="round" stroke-linejoin="round" filter="url(#glow)"/>
                    <circle cx="60" cy="60" r="6" fill="#00ff00" opacity="0.6" filter="url(#glow)"/>
                    <circle cx="452" cy="60" r="6" fill="#00ff00" opacity="0.6" filter="url(#glow)"/>
                </svg>
                <div class="logo">VibeCheck</div>
                <p class="tagline">Slack에서 <strong>Claude Code</strong>를 원격 제어</p>
                <p class="description">
                    서버에서 실행 중인 Claude Code CLI를 Slack DM으로 제어하세요.
                    집, 카페, 이동 중 어디서든 코드를 작성하고 수정할 수 있습니다.
                </p>
                <div style="display: flex; gap: 16px; justify-content: center; flex-wrap: wrap;">
                    <a href="{install_url}" class="btn">Slack에 추가하기</a>
                    <a href="/auth/login" class="btn" style="background: #333; color: #fff; box-shadow: none;">로그인 / 대시보드</a>
                </div>
            </section>
        </div>

        <section class="demo">
            <div class="container">
                <h2>이렇게 동작해요</h2>
                <div class="demo-images">
                    <div class="demo-img-wrapper">
                        <img src="https://raw.githubusercontent.com/NestozAI/VibeCheck/main/assets/ux_demo.png" alt="VibeCheck UX Demo">
                        <p class="demo-img-caption">Slack에서 UI 렌더링, 디자인 수정을 요청하고 즉각적인 시각적 피드백을 받으세요</p>
                    </div>
                    <div class="demo-img-wrapper">
                        <img src="https://raw.githubusercontent.com/NestozAI/VibeCheck/main/assets/architecture.png" alt="VibeCheck Architecture">
                        <p class="demo-img-caption">시스템 아키텍처: Slack - Cloud Server - Local Agent</p>
                    </div>
                </div>
            </div>
        </section>

        <section class="how">
            <div class="container">
                <h2>3단계로 시작하세요</h2>
                <div class="steps">
                    <div class="step">
                        <div class="step-num">1</div>
                        <h3>Slack 앱 설치</h3>
                        <p>"Add to Slack" 버튼을 클릭해 워크스페이스에 VibeCheck을 설치하세요.</p>
                    </div>
                    <div class="step">
                        <div class="step-num">2</div>
                        <h3>Agent 실행</h3>
                        <p>서버에서 <code>pip install vibecheck-agent</code> 후 Agent를 실행하세요.</p>
                    </div>
                    <div class="step">
                        <div class="step-num">3</div>
                        <h3>Slack DM 전송</h3>
                        <p>VibeCheck 봇에게 DM을 보내면 서버의 Claude가 응답합니다.</p>
                    </div>
                </div>
            </div>
        </section>

        <section class="pricing">
            <div class="container">
                <h2>요금제</h2>
                <div class="plans">
                    <div class="plan">
                        <h3>Free</h3>
                        <div class="price">$0<span>/월</span></div>
                        <ul>
                            <li>월 10회 메시지</li>
                            <li>1개 워크스페이스</li>
                            <li>커뮤니티 지원</li>
                        </ul>
                        <a href="{install_url}" class="btn btn-free">무료로 시작</a>
                    </div>
                    <div class="plan pro">
                        <h3>Pro</h3>
                        <div class="price">$10<span>/월</span></div>
                        <ul>
                            <li>무제한 메시지</li>
                            <li>무제한 워크스페이스</li>
                            <li>우선 지원</li>
                            <li>신규 기능 얼리 액세스</li>
                        </ul>
                        <a href="{install_url}" class="btn">Pro 시작하기</a>
                    </div>
                </div>
            </div>
        </section>

        <footer>
            <div class="container">
                <p>VibeCheck by Nestoz</p>
            </div>
        </footer>
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
# Sign in with Slack (유저 로그인)
# =============================================================================

# Sign in with Slack 스코프 (유저 정보 읽기)
USER_SCOPES = ["identity.basic", "identity.email", "identity.avatar"]


@app.get("/auth/login")
async def auth_login():
    """Sign in with Slack 시작"""
    if not SLACK_CLIENT_ID:
        return HTMLResponse("<h1>Error: SLACK_CLIENT_ID not configured</h1>")

    authorize_url = (
        f"https://slack.com/oauth/v2/authorize?"
        f"client_id={SLACK_CLIENT_ID}&"
        f"user_scope={','.join(USER_SCOPES)}&"
        f"redirect_uri={BASE_URL}/auth/callback"
    )
    return RedirectResponse(authorize_url)


@app.get("/auth/callback")
async def auth_callback(code: str = None, error: str = None):
    """Sign in with Slack 콜백"""
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
                "redirect_uri": f"{BASE_URL}/auth/callback"
            }
        )
        data = response.json()

    if not data.get("ok"):
        logger.error(f"Sign in 실패: {data}")
        return HTMLResponse(f"<h1>로그인 실패: {data.get('error')}</h1>")

    # 유저 정보 가져오기
    authed_user = data.get("authed_user", {})
    user_token = authed_user.get("access_token")
    slack_user_id = authed_user.get("id")
    team_id = data.get("team", {}).get("id")

    # Slack API로 유저 프로필 가져오기
    async with httpx.AsyncClient() as client:
        identity_response = await client.get(
            "https://slack.com/api/users.identity",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        identity_data = identity_response.json()

    user_info = identity_data.get("user", {})
    email = user_info.get("email")
    display_name = user_info.get("name")
    avatar_url = user_info.get("image_192")

    db = SessionLocal()
    try:
        # 유저 찾기 또는 생성
        user = db.query(User).filter(
            User.slack_user_id == slack_user_id,
            User.slack_team_id == team_id
        ).first()

        if not user:
            user = User(
                slack_user_id=slack_user_id,
                slack_team_id=team_id,
                email=email,
                display_name=display_name,
                avatar_url=avatar_url
            )
            db.add(user)
        else:
            # 프로필 업데이트
            user.email = email
            user.display_name = display_name
            user.avatar_url = avatar_url

        db.commit()
        db.refresh(user)

        # 세션 생성
        session_token = secrets.token_urlsafe(32)
        session = Session(
            session_token=session_token,
            user_id=user.id,
            expires_at=datetime.utcnow() + timedelta(days=30)
        )
        db.add(session)
        db.commit()

        logger.info(f"유저 로그인: {display_name} ({email})")

        # 대시보드로 리다이렉트 (쿠키 설정)
        response = RedirectResponse("/dashboard", status_code=302)
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            max_age=60 * 60 * 24 * 30,  # 30일
            samesite="lax"
        )
        return response

    finally:
        db.close()


@app.get("/auth/logout")
async def auth_logout(response: Response, session_token: str = Cookie(None)):
    """로그아웃"""
    if session_token:
        db = SessionLocal()
        try:
            session = db.query(Session).filter(Session.session_token == session_token).first()
            if session:
                db.delete(session)
                db.commit()
        finally:
            db.close()

    response = RedirectResponse("/", status_code=302)
    response.delete_cookie("session_token")
    return response


def get_current_user(session_token: str = None):
    """현재 로그인한 유저 가져오기"""
    if not session_token:
        return None

    db = SessionLocal()
    try:
        session = db.query(Session).filter(
            Session.session_token == session_token,
            Session.expires_at > datetime.utcnow()
        ).first()

        if not session:
            return None

        user = db.query(User).filter(User.id == session.user_id).first()
        return user
    finally:
        db.close()


# =============================================================================
# User Dashboard
# =============================================================================

def dashboard_html(user: User) -> str:
    """대시보드 HTML 생성"""
    allowlist = json.loads(user.allowlist) if user.allowlist else DEFAULT_ALLOWLIST.copy()
    allowlist_html = "".join([f'<li><code>{item}</code></li>' for item in allowlist])

    agent_status = "🟢 연결됨" if user.agent_connected else "🔴 연결 안됨"
    plan_badge = '<span class="badge pro">PRO</span>' if user.plan == "pro" else '<span class="badge free">FREE</span>'

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard - VibeCheck</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #0a0a0a;
                color: #e0e0e0;
                min-height: 100vh;
            }}
            .header {{
                background: #111;
                border-bottom: 1px solid #222;
                padding: 16px 24px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .header .logo {{
                font-size: 1.5rem;
                font-weight: 700;
                color: #00ff00;
            }}
            .header .user-info {{
                display: flex;
                align-items: center;
                gap: 12px;
            }}
            .header .avatar {{
                width: 36px;
                height: 36px;
                border-radius: 50%;
            }}
            .header .logout {{
                color: #888;
                text-decoration: none;
                font-size: 0.9rem;
            }}
            .header .logout:hover {{
                color: #fff;
            }}
            .container {{
                max-width: 900px;
                margin: 0 auto;
                padding: 40px 24px;
            }}
            .welcome {{
                margin-bottom: 40px;
            }}
            .welcome h1 {{
                font-size: 1.8rem;
                color: #fff;
                margin-bottom: 8px;
            }}
            .welcome p {{
                color: #888;
            }}
            .card {{
                background: #111;
                border: 1px solid #222;
                border-radius: 12px;
                padding: 24px;
                margin-bottom: 24px;
            }}
            .card h2 {{
                font-size: 1.2rem;
                color: #fff;
                margin-bottom: 16px;
                display: flex;
                align-items: center;
                gap: 8px;
            }}
            .badge {{
                font-size: 0.7rem;
                padding: 4px 8px;
                border-radius: 4px;
                font-weight: 600;
            }}
            .badge.free {{
                background: #333;
                color: #888;
            }}
            .badge.pro {{
                background: #00ff00;
                color: #0a0a0a;
            }}
            .stat-grid {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 16px;
            }}
            .stat {{
                text-align: center;
                padding: 16px;
                background: #1a1a1a;
                border-radius: 8px;
            }}
            .stat .value {{
                font-size: 2rem;
                font-weight: 700;
                color: #00ff00;
            }}
            .stat .label {{
                font-size: 0.85rem;
                color: #666;
                margin-top: 4px;
            }}
            .api-key {{
                background: #1a1a1a;
                padding: 16px;
                border-radius: 8px;
                font-family: monospace;
                font-size: 0.9rem;
                color: #00ff00;
                word-break: break-all;
                position: relative;
            }}
            .api-key .copy-btn {{
                position: absolute;
                right: 12px;
                top: 50%;
                transform: translateY(-50%);
                background: #333;
                border: none;
                color: #fff;
                padding: 8px 12px;
                border-radius: 4px;
                cursor: pointer;
            }}
            .api-key .copy-btn:hover {{
                background: #444;
            }}
            .agent-status {{
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 1.1rem;
            }}
            .allowlist-list {{
                list-style: none;
            }}
            .allowlist-list li {{
                padding: 8px 0;
                border-bottom: 1px solid #222;
            }}
            .allowlist-list li:last-child {{
                border-bottom: none;
            }}
            .allowlist-list code {{
                background: #1a1a1a;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 0.85rem;
            }}
            .setup-code {{
                background: #1a1a1a;
                padding: 16px;
                border-radius: 8px;
                overflow-x: auto;
            }}
            .setup-code pre {{
                color: #00ff00;
                font-size: 0.85rem;
                margin: 0;
            }}
            .btn {{
                display: inline-block;
                background: #00ff00;
                color: #0a0a0a;
                padding: 12px 24px;
                border-radius: 6px;
                text-decoration: none;
                font-weight: 600;
                font-size: 0.9rem;
                border: none;
                cursor: pointer;
            }}
            .btn:hover {{
                opacity: 0.9;
            }}
            .btn-secondary {{
                background: #333;
                color: #fff;
            }}
            @media (max-width: 600px) {{
                .stat-grid {{
                    grid-template-columns: 1fr;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo">VibeCheck</div>
            <div class="user-info">
                <img src="{user.avatar_url or ''}" alt="" class="avatar">
                <span>{user.display_name or user.slack_user_id}</span>
                <a href="/auth/logout" class="logout">로그아웃</a>
            </div>
        </div>
        <div class="container">
            <div class="welcome">
                <h1>안녕하세요, {user.display_name or 'User'}님! {plan_badge}</h1>
                <p>VibeCheck 대시보드에서 Agent 상태와 사용량을 확인하세요.</p>
            </div>

            <div class="card">
                <h2>📊 사용량</h2>
                <div class="stat-grid">
                    <div class="stat">
                        <div class="value">{user.usage_count}</div>
                        <div class="label">사용한 메시지</div>
                    </div>
                    <div class="stat">
                        <div class="value">{user.usage_limit}</div>
                        <div class="label">월 한도</div>
                    </div>
                    <div class="stat">
                        <div class="value">{max(0, user.usage_limit - user.usage_count)}</div>
                        <div class="label">남은 메시지</div>
                    </div>
                </div>
            </div>

            <div class="card">
                <h2>🤖 Agent 상태</h2>
                <div class="agent-status">{agent_status}</div>
            </div>

            <div class="card">
                <h2>🔑 API Key</h2>
                <div class="api-key">
                    {user.api_key}
                    <button class="copy-btn" onclick="navigator.clipboard.writeText('{user.api_key}')">복사</button>
                </div>
            </div>

            <div class="card">
                <h2>🚀 Agent 설치 방법</h2>
                <div class="setup-code">
                    <pre>pip install vibecheck-agent
vibecheck-agent --key={user.api_key}</pre>
                </div>
            </div>

            <div class="card">
                <h2>🔐 Allowlist (허용된 권한)</h2>
                <ul class="allowlist-list">
                    {allowlist_html}
                </ul>
                <p style="color: #666; font-size: 0.85rem; margin-top: 16px;">
                    💡 Slack에서 <code>/permissions</code>를 입력하면 권한을 관리할 수 있습니다.
                </p>
            </div>
        </div>
    </body>
    </html>
    """


@app.get("/dashboard")
async def dashboard(session_token: str = Cookie(None)):
    """유저 대시보드"""
    user = get_current_user(session_token)

    if not user:
        return RedirectResponse("/auth/login")

    return HTMLResponse(dashboard_html(user))


@app.post("/api/regenerate-key")
async def regenerate_api_key(session_token: str = Cookie(None)):
    """API Key 재생성"""
    user = get_current_user(session_token)

    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.id == user.id).first()
        if db_user:
            new_key = f"vibe_sk_{secrets.token_hex(16)}"
            db_user.api_key = new_key
            db.commit()
            return JSONResponse({"api_key": new_key})
    finally:
        db.close()

    return JSONResponse({"error": "Failed"}, status_code=500)


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
                    pending = pending_responses.pop(key, None)  # pop으로 가져오면서 삭제

                    logger.info(f"Agent 응답 수신: key={key[:20]}..., pending={pending is not None}, text_len={len(response_text)}")

                    if pending and response_text:
                        team_id, channel, message_ts = pending
                        client = get_slack_client(team_id)
                        logger.info(f"Slack 클라이언트: team={team_id}, client={client is not None}")

                        if client:
                            try:
                                # Block Kit으로 응답 전송 (처리 중 메시지 업데이트)
                                response_blocks = build_response_blocks(response_text)
                                await client.chat_update(
                                    channel=channel,
                                    ts=message_ts,
                                    text=response_text[:500],
                                    blocks=response_blocks
                                )
                                logger.info(f"Slack으로 응답 전송 성공: {response_text[:50]}...")
                            except Exception as slack_err:
                                logger.error(f"Slack 메시지 업데이트 실패: {slack_err}")
                                # 업데이트 실패 시 새 메시지로 전송 시도
                                try:
                                    await client.chat_postMessage(
                                        channel=channel,
                                        text=response_text[:3000],
                                        blocks=response_blocks
                                    )
                                    logger.info("새 메시지로 응답 전송 성공")
                                except Exception as e2:
                                    logger.error(f"새 메시지 전송도 실패: {e2}")
                    elif not pending:
                        logger.warning(f"pending_responses에 키가 없음: {key[:20]}...")
                    elif not response_text:
                        logger.warning("응답 텍스트가 비어있음")

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
