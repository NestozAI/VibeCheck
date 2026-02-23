
import os
import logging
from typing import Dict
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("vibe-bot")

# =============================================================================
# Environment variables
# =============================================================================

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN", "")
SLACK_ENABLED = bool(SLACK_BOT_TOKEN and SLACK_APP_TOKEN)

WORK_DIR = os.environ.get("WORK_DIR", os.getcwd())
BOT_LANG = os.environ.get("BOT_LANG", "en")

WEB_PORT = int(os.environ.get("WEB_PORT", "8501"))
WEB_HOST = os.environ.get("WEB_HOST", "0.0.0.0")

# =============================================================================
# Multilingual messages
# =============================================================================

MESSAGES = {
    "ko": {
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
    """Return message matching the language setting"""
    use_lang = lang or "ko"
    return MESSAGES.get(use_lang, MESSAGES["ko"]).get(key, MESSAGES["ko"].get(key, key))

# Per-user language settings (can be changed via command)
user_lang_override: Dict[str, str] = {}

def get_user_lang(client=None, user_id: str = None) -> str:
    """Get user's language setting"""
    # 1. Prioritize language set by user via /lang command
    if user_id and user_id in user_lang_override:
        return user_lang_override[user_id]

    # 2. Use fixed language if BOT_LANG is not auto
    if BOT_LANG != "auto":
        return BOT_LANG

    # 3. If auto and Slack client available, follow Slack locale
    if client and user_id:
        try:
            result = client.users_info(user=user_id)
            locale = result.get("user", {}).get("locale", "en-US")
            lang = locale.split("-")[0] if locale else "en"
            if lang not in MESSAGES:
                lang = "en"
            return lang
        except Exception as e:
            logger.warning(f"Failed to look up user language: {e}")

    return "en"

# Safe read-only system commands (can run without approval)
SAFE_SYSTEM_COMMANDS = {
    'nvidia-smi', 'df', 'free', 'uptime', 'whoami', 'hostname',
    'cat /proc/cpuinfo', 'cat /proc/meminfo', 'ps', 'top -bn1',
    'ls', 'pwd', 'date', 'which', 'echo'
}
