
import uuid
import uuid
from typing import List

from config import WORK_DIR
from security import get_trusted_paths, normalize_path

# =============================================================================
# Block Kit UI Builder
# =============================================================================

def build_approval_blocks(task_id: str, untrusted_paths: List[str], user_message: str) -> List[dict]:
    """Path approval request Block Kit UI"""
    path_list = "\n".join([f"• `{p}`" for p in untrusted_paths])

    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"⚠️ *Security Warning*\n\nAI is trying to access the following paths:\n{path_list}"
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"📝 Request: _{user_message[:100]}{'...' if len(user_message) > 100 else ''}_"
                }
            ]
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Approve & Run", "emoji": True},
                    "style": "primary",
                    "action_id": "approve_access",
                    "value": task_id
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Approve (Permanent)", "emoji": True},
                    "action_id": "approve_permanent",
                    "value": task_id
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ Deny", "emoji": True},
                    "style": "danger",
                    "action_id": "deny_access",
                    "value": task_id
                }
            ]
        }
    ]


def build_message_with_delete_button(text: str, message_id: str = None) -> List[dict]:
    """Create message block with delete button"""
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
    """Trusted paths list Block Kit UI"""
    paths = get_trusted_paths()

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🔐 Trusted Paths List", "emoji": True}
        },
        {"type": "divider"}
    ]

    if not paths:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "_No registered paths._"}
        })
    else:
        for path in paths:
            is_default = (normalize_path(path) == normalize_path(WORK_DIR))
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📁 `{path}`" + (" _(default)_" if is_default else "")
                },
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🗑️ Remove", "emoji": True},
                    "style": "danger",
                    "action_id": "remove_trusted_path",
                    "value": path
                } if not is_default else None
            })
            # Remove None accessory
            if blocks[-1]["accessory"] is None:
                del blocks[-1]["accessory"]

    blocks.append({"type": "divider"})
    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": "💡 Add new path: `/trust /path/to/folder`"}
        ]
    })

    return blocks
