"""
Claude Code Bridge Bot
- Slack에서 Claude Code CLI를 원격 제어
- subprocess로 CLI 실행 (--print 모드)
- --continue로 대화 유지
- 🛡️ 경로 기반 보안 승인 시스템
"""

import os
import re
import glob
import json
import time
import logging
import threading
import subprocess
import uuid
from typing import Optional, List, Set, Dict, Any
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
# 🛡️ 보안 시스템: 신뢰 경로 & 승인 대기
# =============================================================================

# 신뢰할 수 있는 경로 (화이트리스트)
TRUSTED_PATHS: Set[str] = {WORK_DIR}  # 기본 작업 디렉토리는 신뢰

# 안전한 읽기 전용 시스템 명령어 (승인 없이 실행 가능)
SAFE_SYSTEM_COMMANDS = {
    'nvidia-smi', 'df', 'free', 'uptime', 'whoami', 'hostname',
    'cat /proc/cpuinfo', 'cat /proc/meminfo', 'ps', 'top -bn1',
    'ls', 'pwd', 'date', 'which', 'echo'
}

# 승인 대기 중인 작업들 (task_id -> task_info)
pending_tasks: Dict[str, Dict[str, Any]] = {}

# Lock for thread safety
trusted_paths_lock = threading.Lock()
pending_tasks_lock = threading.Lock()


def normalize_path(path: str) -> str:
    """경로 정규화"""
    return os.path.normpath(os.path.abspath(os.path.expanduser(path)))


def is_path_trusted(path: str) -> bool:
    """경로가 신뢰할 수 있는지 확인"""
    normalized = normalize_path(path)
    with trusted_paths_lock:
        for trusted in TRUSTED_PATHS:
            trusted_norm = normalize_path(trusted)
            # 신뢰 경로 또는 그 하위 경로인 경우
            if normalized == trusted_norm or normalized.startswith(trusted_norm + os.sep):
                return True
    return False


def add_trusted_path(path: str) -> None:
    """신뢰 경로 추가"""
    normalized = normalize_path(path)
    with trusted_paths_lock:
        TRUSTED_PATHS.add(normalized)
        logger.info(f"🔓 신뢰 경로 추가: {normalized}")


def remove_trusted_path(path: str) -> bool:
    """신뢰 경로 제거"""
    normalized = normalize_path(path)
    with trusted_paths_lock:
        if normalized in TRUSTED_PATHS and normalized != normalize_path(WORK_DIR):
            TRUSTED_PATHS.remove(normalized)
            logger.info(f"🔒 신뢰 경로 제거: {normalized}")
            return True
    return False


def get_trusted_paths() -> List[str]:
    """신뢰 경로 목록 반환"""
    with trusted_paths_lock:
        return sorted(list(TRUSTED_PATHS))


def extract_paths_from_message(message: str) -> List[str]:
    """메시지에서 경로 추출"""
    paths = []

    # 절대 경로 패턴 (/로 시작)
    abs_pattern = r'(/[a-zA-Z0-9_\-./]+)'
    abs_matches = re.findall(abs_pattern, message)
    paths.extend(abs_matches)

    # 상대 경로 패턴 (./나 ../ 로 시작)
    rel_pattern = r'(\.\./[a-zA-Z0-9_\-./]+|\.\/[a-zA-Z0-9_\-./]+)'
    rel_matches = re.findall(rel_pattern, message)
    paths.extend(rel_matches)

    # 파일 확장자가 있는 패턴
    file_pattern = r'([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)'
    file_matches = re.findall(file_pattern, message)
    paths.extend(file_matches)

    # 중복 제거 및 정규화
    unique_paths = []
    seen = set()
    for p in paths:
        # 확장자만 있는 것 제외 (예: .png)
        if p.startswith('.') and '/' not in p:
            continue
        normalized = normalize_path(p) if p.startswith('/') else p
        if normalized not in seen:
            seen.add(normalized)
            unique_paths.append(p)

    return unique_paths


def check_untrusted_paths(message: str) -> List[str]:
    """메시지에서 신뢰되지 않은 경로 찾기"""
    paths = extract_paths_from_message(message)
    untrusted = []

    for path in paths:
        # 절대 경로만 검사
        if path.startswith('/'):
            if not is_path_trusted(path):
                untrusted.append(path)

    return untrusted


def is_safe_system_command(message: str) -> bool:
    """안전한 시스템 명령어인지 확인"""
    msg_lower = message.lower().strip()
    for cmd in SAFE_SYSTEM_COMMANDS:
        if cmd in msg_lower:
            return True
    return False


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
# 이미지 감지 및 업로드
# =============================================================================

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp'}

def get_existing_images(work_dir: str) -> Set[str]:
    """작업 디렉토리의 기존 이미지 파일 목록 반환"""
    existing = set()
    for ext in IMAGE_EXTENSIONS:
        existing.update(glob.glob(os.path.join(work_dir, f'*{ext}')))
        existing.update(glob.glob(os.path.join(work_dir, f'**/*{ext}'), recursive=True))
    return existing

def find_new_images(work_dir: str, before_images: Set[str]) -> List[str]:
    """새로 생성된 이미지 파일 찾기"""
    after_images = get_existing_images(work_dir)
    new_images = after_images - before_images
    return list(new_images)

def extract_image_paths_from_response(response: str, work_dir: str) -> List[str]:
    """Claude 응답에서 이미지 파일 경로 추출 (기존 파일만)"""
    image_paths = []

    # 이미지 확장자 패턴
    ext_pattern = '|'.join([ext.replace('.', r'\.') for ext in IMAGE_EXTENSIONS])

    # 절대 경로 패턴: /path/to/image.png
    abs_pattern = rf'(/[a-zA-Z0-9_\-./]+(?:{ext_pattern}))'
    abs_matches = re.findall(abs_pattern, response, re.IGNORECASE)

    # 상대 경로 패턴: ./image.png, image.png, path/to/image.png
    rel_pattern = rf'(?:^|[\s`\'"(])([a-zA-Z0-9_\-./]+(?:{ext_pattern}))'
    rel_matches = re.findall(rel_pattern, response, re.IGNORECASE)

    all_matches = abs_matches + rel_matches

    for path in all_matches:
        # 경로 정규화
        if path.startswith('/'):
            full_path = path
        else:
            full_path = os.path.join(work_dir, path)

        full_path = os.path.normpath(full_path)

        # 파일이 실제로 존재하는지 확인
        if os.path.isfile(full_path) and full_path not in image_paths:
            image_paths.append(full_path)

    return image_paths


def find_contextual_images(user_message: str, response: str, work_dir: str) -> List[str]:
    """
    사용자 요청과 Claude 응답 컨텍스트를 분석하여 관련 이미지 찾기
    - "그래프 보여줘", "이미지 보여줘" 등의 요청 감지
    - 응답에서 언급된 키워드로 이미지 매칭
    """
    image_paths = []

    # 이미지 요청 키워드
    request_keywords = ['그래프', 'graph', '이미지', 'image', '보여', 'show', '차트', 'chart', 'plot', '시각화']
    combined_text = (user_message + ' ' + response).lower()

    # 키워드가 있는지 확인
    has_image_request = any(kw in combined_text for kw in request_keywords)

    if not has_image_request:
        return []

    # 응답에서 힌트가 될 수 있는 키워드 추출
    hint_patterns = [
        (r'loss[_\s]?curve', 'loss_curve'),
        (r'loss', 'loss'),
        (r'training', 'training'),
        (r'학습', 'loss'),
        (r'그래프', 'graph'),
        (r'chart', 'chart'),
        (r'result', 'result'),
    ]

    # work_dir에서 이미지 파일 찾기
    all_images = get_existing_images(work_dir)

    for img_path in all_images:
        filename = os.path.basename(img_path).lower()

        # 힌트 패턴 매칭
        for pattern, hint in hint_patterns:
            if re.search(pattern, combined_text, re.IGNORECASE):
                if hint in filename or pattern.replace(r'[_\s]?', '').replace('\\', '') in filename:
                    if img_path not in image_paths:
                        image_paths.append(img_path)
                        break

    return image_paths

def upload_images_to_slack(client, channel: str, thread_ts: str, image_paths: List[str], comment_prefix: str = "📊 생성된 이미지"):
    """이미지들을 Slack에 업로드"""
    for image_path in image_paths:
        try:
            filename = os.path.basename(image_path)
            logger.info(f"이미지 업로드 중: {filename}")

            client.files_upload_v2(
                channel=channel,
                file=image_path,
                filename=filename,
                title=filename,
                thread_ts=thread_ts,
                initial_comment=f"{comment_prefix}: `{filename}`"
            )
            logger.info(f"이미지 업로드 완료: {filename}")
        except Exception as e:
            logger.error(f"이미지 업로드 실패 ({image_path}): {e}")


# =============================================================================
# Block Kit UI 빌더
# =============================================================================

def build_approval_blocks(task_id: str, untrusted_paths: List[str], user_message: str) -> List[dict]:
    """경로 승인 요청 Block Kit UI"""
    path_list = "\n".join([f"• `{p}`" for p in untrusted_paths])

    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"⚠️ *보안 경고*\n\nAI가 다음 경로에 접근하려고 합니다:\n{path_list}"
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"📝 요청: _{user_message[:100]}{'...' if len(user_message) > 100 else ''}_"
                }
            ]
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ 승인 및 실행", "emoji": True},
                    "style": "primary",
                    "action_id": "approve_access",
                    "value": task_id
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ 승인 (영구)", "emoji": True},
                    "action_id": "approve_permanent",
                    "value": task_id
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ 거절", "emoji": True},
                    "style": "danger",
                    "action_id": "deny_access",
                    "value": task_id
                }
            ]
        }
    ]


def build_message_with_delete_button(text: str, message_id: str = None) -> List[dict]:
    """삭제 버튼이 있는 메시지 블록 생성"""
    if not message_id:
        message_id = str(uuid.uuid4())[:8]

    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": text}
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🗑️", "emoji": True},
                    "action_id": "delete_message",
                    "value": message_id
                }
            ]
        }
    ]


def build_trusted_paths_blocks() -> List[dict]:
    """신뢰 경로 목록 Block Kit UI"""
    paths = get_trusted_paths()

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🔐 신뢰할 수 있는 경로 목록", "emoji": True}
        },
        {"type": "divider"}
    ]

    if not paths:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "_등록된 경로가 없습니다._"}
        })
    else:
        for path in paths:
            is_default = (normalize_path(path) == normalize_path(WORK_DIR))
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📁 `{path}`" + (" _(기본)_" if is_default else "")
                },
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🗑️ 제거", "emoji": True},
                    "style": "danger",
                    "action_id": "remove_trusted_path",
                    "value": path
                } if not is_default else None
            })
            # None accessory 제거
            if blocks[-1]["accessory"] is None:
                del blocks[-1]["accessory"]

    blocks.append({"type": "divider"})
    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": "💡 새 경로 추가: `/trust /path/to/folder`"}
        ]
    })

    return blocks


# =============================================================================
# Slack 이벤트 핸들러
# =============================================================================

def extract_message_text(event: dict) -> str:
    """멘션 제거 후 메시지 추출"""
    text = event.get("text", "")
    text = re.sub(r'<@[A-Z0-9]+>', '', text).strip()
    return text


def process_and_reply(say, thread_ts: str, user_message: str, client=None, channel: str = None, user_id: str = None):
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
            "• `도움말` 또는 `/help` - 이 도움말\n"
            "• `/paths` - 신뢰 경로 목록 보기\n"
            "• `/trust /path` - 경로 신뢰 목록에 추가\n\n"
            f"*작업 디렉토리:* `{WORK_DIR}`"
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
    thinking_msg = say(text="⏳ Claude가 생각하는 중...", thread_ts=thread_ts)

    # Claude 실행 전 기존 이미지 목록 저장
    before_images = get_existing_images(WORK_DIR)

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
        say(text="🤔 Claude가 응답하지 않았습니다.", thread_ts=thread_ts)

    # 이미지 업로드 처리
    if client and channel:
        uploaded_images = set()

        # 1. 새로 생성된 이미지 업로드
        new_images = find_new_images(WORK_DIR, before_images)
        if new_images:
            logger.info(f"새 이미지 발견: {new_images}")
            upload_images_to_slack(client, channel, thread_ts, new_images, "📊 생성된 이미지")
            uploaded_images.update(new_images)

        # 2. 응답에서 언급된 기존 이미지 업로드
        mentioned_images = extract_image_paths_from_response(response, WORK_DIR)
        # 이미 업로드된 이미지 제외
        mentioned_images = [img for img in mentioned_images if img not in uploaded_images]
        if mentioned_images:
            logger.info(f"응답에서 언급된 이미지: {mentioned_images}")
            upload_images_to_slack(client, channel, thread_ts, mentioned_images, "📎 참조된 이미지")
            uploaded_images.update(mentioned_images)

        # 3. 컨텍스트 기반 이미지 찾기 (그래프 보여줘 등)
        contextual_images = find_contextual_images(user_message, response, WORK_DIR)
        contextual_images = [img for img in contextual_images if img not in uploaded_images]
        if contextual_images:
            logger.info(f"컨텍스트 기반 이미지: {contextual_images}")
            upload_images_to_slack(client, channel, thread_ts, contextual_images, "📎 관련 이미지")


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

    if not claude_runner:
        claude_runner = ClaudeRunner(WORK_DIR)

    # 실행 알림
    client.chat_postMessage(
        channel=channel,
        thread_ts=thread_ts,
        text="⏳ 승인됨! Claude가 실행 중..."
    )

    # Claude 실행 전 기존 이미지 목록 저장
    before_images = get_existing_images(WORK_DIR)

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
            text="🤔 Claude가 응답하지 않았습니다."
        )

    # 이미지 업로드 처리
    uploaded_images = set()

    # 1. 새로 생성된 이미지 업로드
    new_images = find_new_images(WORK_DIR, before_images)
    if new_images:
        logger.info(f"새 이미지 발견: {new_images}")
        upload_images_to_slack(client, channel, thread_ts, new_images, "📊 생성된 이미지")
        uploaded_images.update(new_images)

    # 2. 응답에서 언급된 기존 이미지 업로드
    mentioned_images = extract_image_paths_from_response(response, WORK_DIR)
    mentioned_images = [img for img in mentioned_images if img not in uploaded_images]
    if mentioned_images:
        logger.info(f"응답에서 언급된 이미지: {mentioned_images}")
        upload_images_to_slack(client, channel, thread_ts, mentioned_images, "📎 참조된 이미지")
        uploaded_images.update(mentioned_images)

    # 3. 컨텍스트 기반 이미지 찾기
    contextual_images = find_contextual_images(user_message, response, WORK_DIR)
    contextual_images = [img for img in contextual_images if img not in uploaded_images]
    if contextual_images:
        logger.info(f"컨텍스트 기반 이미지: {contextual_images}")
        upload_images_to_slack(client, channel, thread_ts, contextual_images, "📎 관련 이미지")


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
