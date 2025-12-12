"""
Claude Code Bridge Bot
- Slack에서 Claude Code CLI를 원격 제어
- subprocess로 CLI 실행 (--print 모드)
- --continue로 대화 유지
"""

import os
import re
import time
import logging
import threading
import subprocess
from typing import Optional
from dotenv import load_dotenv

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from cleaner import clean_and_split, clean_output

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

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN")
WORK_DIR = os.environ.get("WORK_DIR", os.getcwd())

if not SLACK_BOT_TOKEN:
    raise ValueError("SLACK_BOT_TOKEN 환경변수가 설정되지 않았습니다.")
if not SLACK_APP_TOKEN:
    raise ValueError("SLACK_APP_TOKEN 환경변수가 설정되지 않았습니다.")

# Slack 앱 초기화
app = App(token=SLACK_BOT_TOKEN)


# =============================================================================
# Claude 실행기
# =============================================================================

class ClaudeRunner:
    """
    Claude CLI를 subprocess로 실행

    --print 모드로 한 번에 실행하고 결과 반환
    --continue로 이전 대화 이어가기
    """

    def __init__(self, work_dir: str):
        self.work_dir = work_dir
        self.session_started = False  # 첫 메시지 이후 True
        self.lock = threading.Lock()

    def run(self, message: str, continue_session: bool = True) -> str:
        """
        Claude에 메시지 전송하고 응답 받기

        Args:
            message: 사용자 메시지
            continue_session: True면 --continue로 이전 대화 이어가기

        Returns:
            Claude의 응답 텍스트
        """
        with self.lock:
            # 기본 명령어
            cmd = [
                "claude",
                "--print",  # non-interactive 모드
                "--dangerously-skip-permissions",  # 권한 프롬프트 건너뛰기
            ]

            # 첫 메시지가 아니면 --continue 추가
            if continue_session and self.session_started:
                cmd.append("--continue")

            # 메시지 추가
            cmd.append(message)

            logger.info(f"Claude 실행: {' '.join(cmd[:4])}... '{message[:50]}...'")

            try:
                # subprocess 실행
                result = subprocess.run(
                    cmd,
                    cwd=self.work_dir,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5분 타임아웃
                    env={**os.environ, 'NO_COLOR': '1'}
                )

                # 첫 메시지 성공 후 세션 시작됨 표시
                if not self.session_started:
                    self.session_started = True

                # stdout과 stderr 합치기
                output = result.stdout
                if result.stderr:
                    logger.warning(f"Claude stderr: {result.stderr[:200]}")

                if result.returncode != 0:
                    logger.error(f"Claude 실행 실패 (code {result.returncode}): {result.stderr}")
                    return f"❌ Claude 오류: {result.stderr or '알 수 없는 오류'}"

                logger.info(f"Claude 응답 ({len(output)}자): {output[:100]}...")
                return output

            except subprocess.TimeoutExpired:
                logger.error("Claude 타임아웃 (5분)")
                return "❌ Claude 응답 타임아웃 (5분 초과)"
            except Exception as e:
                logger.error(f"Claude 실행 오류: {e}")
                return f"❌ Claude 실행 오류: {str(e)}"

    def reset_session(self):
        """세션 리셋 (새 대화 시작)"""
        with self.lock:
            self.session_started = False
            logger.info("Claude 세션 리셋됨")


# 전역 Claude 실행기
claude_runner: Optional[ClaudeRunner] = None


# =============================================================================
# Slack 이벤트 핸들러
# =============================================================================

def extract_message_text(event: dict) -> str:
    """멘션 제거 후 메시지 추출"""
    text = event.get("text", "")
    text = re.sub(r'<@[A-Z0-9]+>', '', text).strip()
    return text


def process_and_reply(say, thread_ts: str, user_message: str):
    """Claude 실행하고 응답 전송"""
    global claude_runner

    if not claude_runner:
        claude_runner = ClaudeRunner(WORK_DIR)

    # 특수 명령어 처리
    msg_lower = user_message.lower().strip()

    if msg_lower in ["/reset", "리셋", "새대화", "reset"]:
        claude_runner.reset_session()
        say(text="🔄 새 대화를 시작합니다!", thread_ts=thread_ts)
        return

    if msg_lower in ["/help", "도움말", "help"]:
        say(text=(
            "🤖 *Claude Code Bridge Bot*\n\n"
            "*사용법:*\n"
            "• 메시지를 보내면 Claude가 응답합니다\n"
            "• 대화는 자동으로 이어집니다\n\n"
            "*명령어:*\n"
            "• `리셋` 또는 `/reset` - 새 대화 시작\n"
            "• `도움말` 또는 `/help` - 이 도움말\n\n"
            f"*작업 디렉토리:* `{WORK_DIR}`"
        ), thread_ts=thread_ts)
        return

    # 처리 중 메시지
    say(text="⏳ Claude가 생각하는 중...", thread_ts=thread_ts)

    # Claude 실행
    response = claude_runner.run(user_message)

    # 응답 정제 및 전송
    cleaned = clean_output(response)
    if cleaned:
        # 긴 메시지 분할
        messages = clean_and_split(cleaned)
        for msg in messages:
            if msg.strip():
                say(text=msg, thread_ts=thread_ts)
    else:
        say(text="🤔 Claude가 응답하지 않았습니다.", thread_ts=thread_ts)


@app.event("app_mention")
def handle_mention(event, say, client):
    """봇 멘션 처리"""
    logger.info(f"멘션 수신: {event}")

    user_message = extract_message_text(event)
    thread_ts = event.get("thread_ts", event.get("ts"))

    if not user_message:
        say(text="무엇을 도와드릴까요? 🤔", thread_ts=thread_ts)
        return

    process_and_reply(say, thread_ts, user_message)


@app.event("message")
def handle_message(event, say, client):
    """DM 메시지 처리"""
    # 봇 자신의 메시지 무시
    if event.get("bot_id"):
        return

    # DM만 처리
    if event.get("channel_type") != "im":
        return

    logger.info(f"DM 수신: {event}")

    user_message = event.get("text", "").strip()
    if not user_message:
        return

    thread_ts = event.get("thread_ts", event.get("ts"))

    process_and_reply(say, thread_ts, user_message)


@app.event("app_home_opened")
def handle_app_home(event, client):
    """앱 홈 탭"""
    user_id = event["user"]

    session_status = "✅ 대화 진행 중" if (claude_runner and claude_runner.session_started) else "🆕 새 대화"

    client.views_publish(
        user_id=user_id,
        view={
            "type": "home",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🤖 Claude Code Bridge Bot",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "로컬 서버의 Claude Code CLI를 슬랙에서 원격 제어합니다."
                    }
                },
                {
                    "type": "divider"
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*세션 상태:* {session_status}\n*작업 디렉토리:* `{WORK_DIR}`"
                    }
                },
                {
                    "type": "divider"
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*사용법:*\n"
                               "• DM으로 메시지를 보내면 Claude가 응답합니다\n"
                               "• 채널에서 `@bot 메시지`로 멘션하세요\n"
                               "• 대화는 `--continue`로 자동 이어집니다\n\n"
                               "*명령어:*\n"
                               "• `리셋` - 새 대화 시작\n"
                               "• `도움말` - 도움말 보기"
                    }
                }
            ]
        }
    )


# =============================================================================
# 메인
# =============================================================================

def main():
    """메인 함수"""
    global claude_runner

    logger.info("=" * 50)
    logger.info("🚀 Claude Code Bridge Bot 시작!")
    logger.info(f"📂 작업 디렉토리: {WORK_DIR}")
    logger.info("=" * 50)

    # Claude 실행기 초기화
    claude_runner = ClaudeRunner(WORK_DIR)
    logger.info("✅ Claude 실행기 준비 완료")

    # Slack 핸들러 시작
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)

    try:
        logger.info("⚡️ Slack 연결 중...")
        handler.start()
    except KeyboardInterrupt:
        logger.info("종료 신호 수신")
    finally:
        logger.info("👋 Bridge Bot 종료")


if __name__ == "__main__":
    main()
