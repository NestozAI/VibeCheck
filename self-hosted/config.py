
import os
import logging
from typing import Dict
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("vibe-bot")

# =============================================================================
# 환경변수
# =============================================================================

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN")
WORK_DIR = os.environ.get("WORK_DIR", os.getcwd())
BOT_LANG = os.environ.get("BOT_LANG", "auto")  # auto, ko, en (auto = Slack 로케일 따름)

if not SLACK_BOT_TOKEN:
    raise ValueError("SLACK_BOT_TOKEN 환경변수가 설정되지 않았습니다.")
if not SLACK_APP_TOKEN:
    raise ValueError("SLACK_APP_TOKEN 환경변수가 설정되지 않았습니다.")

# =============================================================================
# 다국어 메시지
# =============================================================================

MESSAGES = {
    "ko": {
        "thinking": "⏳ Claude가 생각하는 중...",
        "approved_running": "⏳ 승인됨! Claude가 실행 중...",
        "no_response": "🤔 Claude가 응답하지 않았습니다.",
        "image_generated": "📊 생성된 이미지",
        "image_referenced": "📎 참조된 이미지",
        "image_related": "📎 관련 이미지",
        "security_warning": "⚠️ *보안 경고*\n\nAI가 다음 경로에 접근하려고 합니다:",
        "request_label": "📝 요청:",
        "btn_approve_run": "✅ 승인 및 실행",
        "btn_approve_permanent": "✅ 승인 (영구)",
        "btn_deny": "❌ 거절",
        "paths_title": "📂 *신뢰 경로 목록*",
        "paths_empty": "등록된 신뢰 경로가 없습니다.",
        "path_added": "✅ 신뢰 경로 추가됨:",
        "path_already": "ℹ️ 이미 신뢰 경로입니다:",
        "path_invalid": "⚠️ 유효하지 않은 경로입니다:",
        "trust_usage": "사용법: `/trust /경로/이름`",
        "help_title": "🤖 *VibeCheck 도움말*",
    },
    "en": {
        "thinking": "⏳ Claude is thinking...",
        "approved_running": "⏳ Approved! Claude is running...",
        "no_response": "🤔 Claude did not respond.",
        "image_generated": "📊 Generated image",
        "image_referenced": "📎 Referenced image",
        "image_related": "📎 Related image",
        "security_warning": "⚠️ *Security Warning*\n\nAI is trying to access the following paths:",
        "request_label": "📝 Request:",
        "btn_approve_run": "✅ Approve & Run",
        "btn_approve_permanent": "✅ Approve (Permanent)",
        "btn_deny": "❌ Deny",
        "paths_title": "📂 *Trusted Paths*",
        "paths_empty": "No trusted paths registered.",
        "path_added": "✅ Trusted path added:",
        "path_already": "ℹ️ Already a trusted path:",
        "path_invalid": "⚠️ Invalid path:",
        "trust_usage": "Usage: `/trust /path/name`",
        "help_title": "🤖 *VibeCheck Help*",
    }
}

def get_msg(key: str, lang: str = None) -> str:
    """언어 설정에 맞는 메시지 반환"""
    use_lang = lang or "ko"
    return MESSAGES.get(use_lang, MESSAGES["ko"]).get(key, MESSAGES["ko"].get(key, key))

# 사용자별 언어 설정 (명령어로 변경 가능)
user_lang_override: Dict[str, str] = {}

def get_user_lang(client, user_id: str) -> str:
    """사용자의 언어 설정 가져오기"""
    # 1. 사용자가 /lang 명령어로 설정한 언어 우선
    if user_id in user_lang_override:
        return user_lang_override[user_id]

    # 2. BOT_LANG이 auto가 아니면 고정 언어 사용
    if BOT_LANG != "auto":
        return BOT_LANG

    # 3. auto면 Slack 로케일 따름
    try:
        result = client.users_info(user=user_id)
        locale = result.get("user", {}).get("locale", "ko-KR")
        lang = locale.split("-")[0] if locale else "ko"
        if lang not in MESSAGES:
            lang = "en" if lang != "ko" else "ko"
        # logger.info(f"사용자 {user_id} 로케일: {locale} -> {lang}")
        return lang
    except Exception as e:
        logger.warning(f"사용자 언어 조회 실패: {e}")
        return "ko"

# 안전한 읽기 전용 시스템 명령어 (승인 없이 실행 가능)
SAFE_SYSTEM_COMMANDS = {
    'nvidia-smi', 'df', 'free', 'uptime', 'whoami', 'hostname',
    'cat /proc/cpuinfo', 'cat /proc/meminfo', 'ps', 'top -bn1',
    'ls', 'pwd', 'date', 'which', 'echo'
}
