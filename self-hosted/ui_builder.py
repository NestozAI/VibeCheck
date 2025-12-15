
import uuid
import uuid
from typing import List

from config import WORK_DIR
from security import get_trusted_paths, normalize_path

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
