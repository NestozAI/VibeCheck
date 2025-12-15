"""
Claude Code Bridge Bot
- Slack에서 Claude Code CLI를 원격 제어
- subprocess로 CLI 실행 (--print 모드)
- --continue로 대화 유지
- 🛡️ 경로 기반 보안 승인 시스템
"""

import time
import logging
import uuid
from typing import Optional

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from config import SLACK_BOT_TOKEN, SLACK_APP_TOKEN, WORK_DIR, get_msg, get_user_lang, user_lang_override
from security import (
    add_trusted_path, remove_trusted_path, get_trusted_paths,
    check_untrusted_paths, is_safe_system_command,
    pending_tasks, pending_tasks_lock
)
from claude_handler import ClaudeRunner
from image_handler import (
    get_images_with_mtime, find_new_or_modified_images,
    extract_image_paths_from_response, find_contextual_images,
    upload_images_to_slack
)
from ui_builder import (
    build_approval_blocks, build_message_with_delete_button,
    build_trusted_paths_blocks
)
from cleaner import clean_and_split, clean_output

# 로깅 설정 (config에서 이미 basicConfig 호출됨)
logger = logging.getLogger(__name__)

# Slack 앱 초기화
app = App(token=SLACK_BOT_TOKEN)

# 전역 Claude 실행기
claude_runner: Optional[ClaudeRunner] = None


# =============================================================================
# Helper Functions
# =============================================================================

def extract_message_text(event: dict) -> str:
    """멘션 제거 후 메시지 추출"""
    text = event.get("text", "")
    import re
    text = re.sub(r'<@[A-Z0-9]+>', '', text).strip()
    return text


def process_and_reply(say, thread_ts: str, user_message: str, client=None, channel: str = None, user_id: str = None):
    """Claude 실행하고 응답 전송"""
    global claude_runner

    if not claude_runner:
        claude_runner = ClaudeRunner(WORK_DIR)

    # 사용자 언어 설정 가져오기
    lang = get_user_lang(client, user_id) if client and user_id else "ko"

    # 특수 명령어 처리
    msg_lower = user_message.lower().strip()

    if msg_lower in ["/reset", "리셋", "새대화", "reset"]:
        claude_runner.reset_session()
        reset_msg = "🔄 Starting a new conversation!" if lang == "en" else "🔄 새 대화를 시작합니다!"
        say(text=reset_msg, thread_ts=thread_ts)
        return

    if msg_lower in ["/help", "도움말", "help"]:
        say(text=(
            f"{get_msg('help_title', lang)}\n\n"
            + ("*Usage:*\n• Send a message and Claude will respond\n• Conversations are automatically continued\n\n"
               "*Commands:*\n• `reset` or `/reset` - Start new conversation\n• `help` or `/help` - This help\n"
               "• `/paths` - View trusted paths\n• `/trust /path` - Add path to trusted list\n\n"
               if lang == "en" else
               "*사용법:*\n• 메시지를 보내면 Claude가 응답합니다\n• 대화는 자동으로 이어집니다\n\n"
               "*명령어:*\n• `리셋` 또는 `/reset` - 새 대화 시작\n• `도움말` 또는 `/help` - 이 도움말\n"
               "• `/paths` - 신뢰 경로 목록 보기\n• `/trust /path` - 경로 신뢰 목록에 추가\n\n")
            + f"*{'Working Directory' if lang == 'en' else '작업 디렉토리'}:* `{WORK_DIR}`"
        ), thread_ts=thread_ts)
        return

    if msg_lower == "/paths" or msg_lower == "경로":
        blocks = build_trusted_paths_blocks()
        say(blocks=blocks, text="신뢰 경로 목록", thread_ts=thread_ts)
        return

    if msg_lower.startswith("/trust "):
        path = user_message[7:].strip()
        if path:
            add_trusted_path(path)
            say(text=f"✅ 신뢰 경로에 추가되었습니다: `{path}`", thread_ts=thread_ts)
        else:
            say(text="❌ 경로를 입력해주세요. 예: `/trust /home/user/project`", thread_ts=thread_ts)
        return

    # 언어 설정 명령어
    if msg_lower.startswith("/lang"):
        parts = msg_lower.split()
        if len(parts) == 2 and parts[1] in ["en", "ko"]:
            user_lang_override[user_id] = parts[1]
            if parts[1] == "en":
                say(text="✅ Language set to English", thread_ts=thread_ts)
            else:
                say(text="✅ 언어가 한국어로 설정되었습니다", thread_ts=thread_ts)
        else:
            say(text="Usage: `/lang en` or `/lang ko`\n사용법: `/lang en` 또는 `/lang ko`", thread_ts=thread_ts)
        return

    # 🛡️ 보안 검사: 신뢰되지 않은 경로 확인
    untrusted_paths = check_untrusted_paths(user_message)

    # 안전한 시스템 명령어는 통과
    if untrusted_paths and not is_safe_system_command(user_message):
        # 승인 필요
        task_id = str(uuid.uuid4())[:8]

        with pending_tasks_lock:
            pending_tasks[task_id] = {
                "message": user_message,
                "thread_ts": thread_ts,
                "channel": channel,
                "user_id": user_id,
                "untrusted_paths": untrusted_paths,
                "timestamp": time.time()
            }

        logger.info(f"🛡️ 승인 대기: {task_id} - 경로: {untrusted_paths}")

        blocks = build_approval_blocks(task_id, untrusted_paths, user_message)
        say(blocks=blocks, text="보안 승인 필요", thread_ts=thread_ts)
        return

    # 처리 중 메시지
    thinking_msg = say(text=get_msg("thinking", lang), thread_ts=thread_ts)

    # Claude 실행 전 기존 이미지 목록 저장 (수정 시간 포함)
    before_images = get_images_with_mtime(WORK_DIR)

    # Claude 실행
    response = claude_runner.run(user_message)

    # "생각하는 중" 메시지 삭제
    if thinking_msg and client and channel:
        try:
            client.chat_delete(channel=channel, ts=thinking_msg.get("ts"))
        except Exception as e:
            logger.warning(f"생각 중 메시지 삭제 실패: {e}")

    # 응답 정제 및 전송
    cleaned = clean_output(response)
    if cleaned:
        # 긴 메시지 분할
        messages = clean_and_split(cleaned)
        for msg in messages:
            if msg.strip():
                # 삭제 버튼과 함께 메시지 전송
                blocks = build_message_with_delete_button(msg)
                say(blocks=blocks, text=msg, thread_ts=thread_ts)
    else:
        say(text=get_msg("no_response", lang), thread_ts=thread_ts)

    # 이미지 업로드 처리
    if client and channel:
        uploaded_images = set()

        # 1. 새로 생성되거나 수정된 이미지 업로드
        new_images = find_new_or_modified_images(WORK_DIR, before_images)
        if new_images:
            logger.info(f"새/수정된 이미지 발견: {new_images}")
            upload_images_to_slack(client, channel, thread_ts, new_images, get_msg("image_generated", lang))
            uploaded_images.update(new_images)

        # 2. 응답에서 언급된 기존 이미지 업로드
        mentioned_images = extract_image_paths_from_response(response, WORK_DIR)
        # 이미 업로드된 이미지 제외
        mentioned_images = [img for img in mentioned_images if img not in uploaded_images]
        if mentioned_images:
            logger.info(f"응답에서 언급된 이미지: {mentioned_images}")
            upload_images_to_slack(client, channel, thread_ts, mentioned_images, get_msg("image_referenced", lang))
            uploaded_images.update(mentioned_images)

        # 3. 컨텍스트 기반 이미지 찾기 (그래프 보여줘 등)
        contextual_images = find_contextual_images(user_message, response, WORK_DIR)
        contextual_images = [img for img in contextual_images if img not in uploaded_images]
        if contextual_images:
            logger.info(f"컨텍스트 기반 이미지: {contextual_images}")
            upload_images_to_slack(client, channel, thread_ts, contextual_images, get_msg("image_related", lang))


def execute_pending_task(task_id: str, client, permanent: bool = False):
    """대기 중인 작업 실행"""
    global claude_runner

    with pending_tasks_lock:
        task = pending_tasks.pop(task_id, None)

    if not task:
        logger.warning(f"작업을 찾을 수 없음: {task_id}")
        return

    # 영구 승인이면 경로 추가
    if permanent:
        for path in task["untrusted_paths"]:
            add_trusted_path(path)

    channel = task["channel"]
    thread_ts = task["thread_ts"]
    user_message = task["message"]
    user_id = task.get("user_id")

    # 사용자 언어 설정
    lang = get_user_lang(client, user_id) if user_id else "ko"

    if not claude_runner:
        claude_runner = ClaudeRunner(WORK_DIR)

    # 실행 알림
    client.chat_postMessage(
        channel=channel,
        thread_ts=thread_ts,
        text=get_msg("approved_running", lang)
    )

    # Claude 실행 전 기존 이미지 목록 저장 (수정 시간 포함)
    before_images = get_images_with_mtime(WORK_DIR)

    # Claude 실행
    response = claude_runner.run(user_message)

    # 응답 정제 및 전송
    cleaned = clean_output(response)
    if cleaned:
        messages = clean_and_split(cleaned)
        for msg in messages:
            if msg.strip():
                # 삭제 버튼과 함께 메시지 전송
                blocks = build_message_with_delete_button(msg)
                client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    blocks=blocks,
                    text=msg
                )
    else:
        client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=get_msg("no_response", lang)
        )

    # 이미지 업로드 처리
    uploaded_images = set()

    # 1. 새로 생성되거나 수정된 이미지 업로드
    new_images = find_new_or_modified_images(WORK_DIR, before_images)
    if new_images:
        logger.info(f"새/수정된 이미지 발견: {new_images}")
        upload_images_to_slack(client, channel, thread_ts, new_images, get_msg("image_generated", lang))
        uploaded_images.update(new_images)

    # 2. 응답에서 언급된 기존 이미지 업로드
    mentioned_images = extract_image_paths_from_response(response, WORK_DIR)
    mentioned_images = [img for img in mentioned_images if img not in uploaded_images]
    if mentioned_images:
        logger.info(f"응답에서 언급된 이미지: {mentioned_images}")
        upload_images_to_slack(client, channel, thread_ts, mentioned_images, get_msg("image_referenced", lang))
        uploaded_images.update(mentioned_images)

    # 3. 컨텍스트 기반 이미지 찾기
    contextual_images = find_contextual_images(user_message, response, WORK_DIR)
    contextual_images = [img for img in contextual_images if img not in uploaded_images]
    if contextual_images:
        logger.info(f"컨텍스트 기반 이미지: {contextual_images}")
        upload_images_to_slack(client, channel, thread_ts, contextual_images, get_msg("image_related", lang))


# =============================================================================
# Slack 이벤트 핸들러
# =============================================================================

@app.event("app_mention")
def handle_mention(event, say, client):
    """봇 멘션 처리"""
    logger.info(f"멘션 수신: {event}")

    user_message = extract_message_text(event)
    thread_ts = event.get("thread_ts", event.get("ts"))
    channel = event.get("channel")
    user_id = event.get("user")

    if not user_message:
        say(text="무엇을 도와드릴까요? 🤔", thread_ts=thread_ts)
        return

    process_and_reply(say, thread_ts, user_message, client=client, channel=channel, user_id=user_id)


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
    channel = event.get("channel")
    user_id = event.get("user")

    process_and_reply(say, thread_ts, user_message, client=client, channel=channel, user_id=user_id)


# =============================================================================
# 버튼 액션 핸들러
# =============================================================================

@app.action("approve_access")
def handle_approve_access(ack, body, client):
    """일회성 승인"""
    ack()

    task_id = body["actions"][0]["value"]
    user = body["user"]["username"]

    logger.info(f"✅ 승인됨 (일회성): {task_id} by {user}")

    # 버튼 메시지 업데이트
    client.chat_update(
        channel=body["channel"]["id"],
        ts=body["message"]["ts"],
        text=f"✅ 승인됨 (일회성) by @{user}",
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"✅ *승인됨* (일회성) by @{user}"}
            }
        ]
    )

    # 작업 실행
    execute_pending_task(task_id, client, permanent=False)


@app.action("approve_permanent")
def handle_approve_permanent(ack, body, client):
    """영구 승인 (경로 추가)"""
    ack()

    task_id = body["actions"][0]["value"]
    user = body["user"]["username"]

    logger.info(f"✅ 승인됨 (영구): {task_id} by {user}")

    # 버튼 메시지 업데이트
    client.chat_update(
        channel=body["channel"]["id"],
        ts=body["message"]["ts"],
        text=f"✅ 승인됨 (영구) by @{user}",
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"✅ *승인됨* (영구 - 경로 신뢰 목록 추가) by @{user}"}
            }
        ]
    )

    # 작업 실행 (영구 승인)
    execute_pending_task(task_id, client, permanent=True)


@app.action("deny_access")
def handle_deny_access(ack, body, client):
    """접근 거절"""
    ack()

    task_id = body["actions"][0]["value"]
    user = body["user"]["username"]

    logger.info(f"❌ 거절됨: {task_id} by {user}")

    # 대기 작업 제거
    with pending_tasks_lock:
        pending_tasks.pop(task_id, None)

    # 버튼 메시지 업데이트
    client.chat_update(
        channel=body["channel"]["id"],
        ts=body["message"]["ts"],
        text=f"❌ 거절됨 by @{user}",
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"❌ *거절됨* by @{user}"}
            }
        ]
    )


@app.action("remove_trusted_path")
def handle_remove_trusted_path(ack, body, client):
    """신뢰 경로 제거"""
    ack()

    path = body["actions"][0]["value"]
    user = body["user"]["username"]

    if remove_trusted_path(path):
        logger.info(f"🗑️ 경로 제거됨: {path} by {user}")

        # 업데이트된 목록 표시
        blocks = build_trusted_paths_blocks()
        client.chat_update(
            channel=body["channel"]["id"],
            ts=body["message"]["ts"],
            text="신뢰 경로 목록",
            blocks=blocks
        )
    else:
        client.chat_postMessage(
            channel=body["channel"]["id"],
            text=f"❌ 기본 경로는 제거할 수 없습니다: `{path}`"
        )


@app.action("delete_message")
def handle_delete_message(ack, body, client):
    """메시지 삭제"""
    ack()

    channel = body["channel"]["id"]
    message_ts = body["message"]["ts"]
    user = body["user"]["username"]

    try:
        client.chat_delete(channel=channel, ts=message_ts)
        logger.info(f"🗑️ 메시지 삭제됨: {message_ts} by {user}")
    except Exception as e:
        logger.error(f"메시지 삭제 실패: {e}")
        # 삭제 실패 시 사용자에게 알림
        try:
            client.chat_postEphemeral(
                channel=channel,
                user=body["user"]["id"],
                text=f"❌ 메시지 삭제 실패: {str(e)}"
            )
        except:
            pass


@app.event("app_home_opened")
def handle_app_home(event, client):
    """앱 홈 탭"""
    user_id = event["user"]

    session_status = "✅ 대화 진행 중" if (claude_runner and claude_runner.session_started) else "🆕 새 대화"
    trusted_count = len(get_trusted_paths())

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
                        "text": f"*세션 상태:* {session_status}\n*작업 디렉토리:* `{WORK_DIR}`\n*신뢰 경로:* {trusted_count}개"
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
                               "• `도움말` - 도움말 보기\n"
                               "• `/paths` - 신뢰 경로 목록\n"
                               "• `/trust /path` - 경로 신뢰 추가\n\n"
                               "*🛡️ 보안:*\n"
                               "• 신뢰되지 않은 경로 접근 시 승인 요청됨\n"
                               "• 시스템 모니터링 명령은 자동 허용"
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
    logger.info(f"🔐 신뢰 경로: {get_trusted_paths()}")
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
