"""
VibeCheck Slack Handler - loaded only when Slack tokens are configured.
Extracts all Slack-specific logic from the original main.py.
"""

import re
import logging

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from config import SLACK_BOT_TOKEN, SLACK_APP_TOKEN, WORK_DIR, get_msg, get_user_lang, user_lang_override
from security import (
    remove_trusted_path, get_trusted_paths,
    pending_tasks, pending_tasks_lock,
)
from image_handler import upload_images_to_slack
from ui_builder import (
    build_approval_blocks, build_message_with_delete_button,
    build_trusted_paths_blocks,
)
from core import VibeCheckCore

logger = logging.getLogger(__name__)


def create_slack_app(core: VibeCheckCore) -> SocketModeHandler:
    """Create and configure a Slack Bolt app using the shared core."""
    app = App(token=SLACK_BOT_TOKEN)

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _extract_message_text(event: dict) -> str:
        text = event.get("text", "")
        text = re.sub(r'<@[A-Z0-9]+>', '', text).strip()
        return text

    # ------------------------------------------------------------------
    # Core message processing via shared VibeCheckCore
    # ------------------------------------------------------------------

    def _process(say, thread_ts, user_message, client=None, channel=None, user_id=None):
        lang = get_user_lang(client, user_id) if client and user_id else "en"
        msg_lower = user_message.lower().strip()

        # Language setting command (Slack-only)
        if msg_lower.startswith("/lang"):
            parts = msg_lower.split()
            if len(parts) == 2 and parts[1] in ["en", "ko"]:
                user_lang_override[user_id] = parts[1]
                say(text=f"Language set to {'English' if parts[1] == 'en' else 'Korean'}", thread_ts=thread_ts)
            else:
                say(text="Usage: `/lang en` or `/lang ko`", thread_ts=thread_ts)
            return

        # Trusted paths list (Slack block kit version)
        if msg_lower == "/paths":
            blocks = build_trusted_paths_blocks()
            say(blocks=blocks, text="Trusted paths list", thread_ts=thread_ts)
            return

        # Delegate to core with Slack-specific callbacks
        thinking_msg = None

        def on_thinking():
            nonlocal thinking_msg
            thinking_msg = say(text=get_msg("thinking", lang), thread_ts=thread_ts)

        def on_response(text):
            # Delete thinking message
            if thinking_msg and client and channel:
                try:
                    client.chat_delete(channel=channel, ts=thinking_msg.get("ts"))
                except Exception:
                    pass
            blocks = build_message_with_delete_button(text)
            say(blocks=blocks, text=text, thread_ts=thread_ts)

        def on_images(paths):
            if client and channel:
                upload_images_to_slack(
                    client, channel, thread_ts, paths,
                    get_msg("image_generated", lang),
                )

        def on_approval_required(task_id, untrusted_paths, user_msg):
            # Store Slack-specific context in pending task
            with pending_tasks_lock:
                if task_id in pending_tasks:
                    pending_tasks[task_id]["thread_ts"] = thread_ts
                    pending_tasks[task_id]["channel"] = channel
                    pending_tasks[task_id]["user_id"] = user_id
            blocks = build_approval_blocks(task_id, untrusted_paths, user_msg)
            say(blocks=blocks, text="Security approval required", thread_ts=thread_ts)

        core.handle_message(
            user_message,
            lang=lang,
            on_thinking=on_thinking,
            on_response=on_response,
            on_images=on_images,
            on_approval_required=on_approval_required,
        )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    @app.event("app_mention")
    def handle_mention(event, say, client):
        user_message = _extract_message_text(event)
        thread_ts = event.get("thread_ts", event.get("ts"))
        channel = event.get("channel")
        user_id = event.get("user")
        if not user_message:
            say(text="How can I help you?", thread_ts=thread_ts)
            return
        _process(say, thread_ts, user_message, client=client, channel=channel, user_id=user_id)

    @app.event("message")
    def handle_message(event, say, client):
        if event.get("bot_id"):
            return
        if event.get("channel_type") != "im":
            return
        user_message = event.get("text", "").strip()
        if not user_message:
            return
        thread_ts = event.get("thread_ts", event.get("ts"))
        channel = event.get("channel")
        user_id = event.get("user")
        _process(say, thread_ts, user_message, client=client, channel=channel, user_id=user_id)

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    @app.action("approve_access")
    def handle_approve_access(ack, body, client):
        ack()
        task_id = body["actions"][0]["value"]
        user = body["user"]["username"]
        client.chat_update(
            channel=body["channel"]["id"],
            ts=body["message"]["ts"],
            text=f"Approved (one-time) by @{user}",
            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": f"Approved (one-time) by @{user}"}}],
        )
        _execute_approved(task_id, client, permanent=False)

    @app.action("approve_permanent")
    def handle_approve_permanent(ack, body, client):
        ack()
        task_id = body["actions"][0]["value"]
        user = body["user"]["username"]
        client.chat_update(
            channel=body["channel"]["id"],
            ts=body["message"]["ts"],
            text=f"Approved (permanent) by @{user}",
            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": f"Approved (permanent) by @{user}"}}],
        )
        _execute_approved(task_id, client, permanent=True)

    @app.action("deny_access")
    def handle_deny_access(ack, body, client):
        ack()
        task_id = body["actions"][0]["value"]
        user = body["user"]["username"]
        with pending_tasks_lock:
            pending_tasks.pop(task_id, None)
        client.chat_update(
            channel=body["channel"]["id"],
            ts=body["message"]["ts"],
            text=f"Denied by @{user}",
            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": f"Denied by @{user}"}}],
        )

    @app.action("remove_trusted_path")
    def handle_remove_trusted_path(ack, body, client):
        ack()
        path = body["actions"][0]["value"]
        if remove_trusted_path(path):
            blocks = build_trusted_paths_blocks()
            client.chat_update(
                channel=body["channel"]["id"],
                ts=body["message"]["ts"],
                text="Trusted paths list",
                blocks=blocks,
            )
        else:
            client.chat_postMessage(
                channel=body["channel"]["id"],
                text=f"Cannot remove the default path: `{path}`",
            )

    @app.action("delete_message")
    def handle_delete_message(ack, body, client):
        ack()
        try:
            client.chat_delete(channel=body["channel"]["id"], ts=body["message"]["ts"])
        except Exception as e:
            logger.error(f"Message deletion failed: {e}")

    # ------------------------------------------------------------------
    # App Home
    # ------------------------------------------------------------------

    @app.event("app_home_opened")
    def handle_app_home(event, client):
        user_id = event["user"]
        session_status = (
            "Conversation in progress"
            if core.claude_runner and core.claude_runner.session_started
            else "New conversation"
        )
        trusted_count = len(get_trusted_paths())

        client.views_publish(
            user_id=user_id,
            view={
                "type": "home",
                "blocks": [
                    {"type": "header", "text": {"type": "plain_text", "text": "VibeCheck", "emoji": True}},
                    {"type": "section", "text": {"type": "mrkdwn", "text": "Remotely control the Claude Code CLI from Slack."}},
                    {"type": "divider"},
                    {"type": "section", "text": {"type": "mrkdwn", "text": (
                        f"*Session:* {session_status}\n"
                        f"*Working directory:* `{WORK_DIR}`\n"
                        f"*Trusted paths:* {trusted_count}"
                    )}},
                    {"type": "divider"},
                    {"type": "section", "text": {"type": "mrkdwn", "text": (
                        "*Usage:*\n"
                        "- Send a DM and Claude will respond\n"
                        "- Mention `@bot message` in a channel\n\n"
                        "*Commands:*\n"
                        "- `reset` - Start new conversation\n"
                        "- `help` - Show help\n"
                        "- `/paths` - Trusted paths list\n"
                        "- `/trust /path` - Add trusted path"
                    )}},
                ],
            },
        )

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _execute_approved(task_id: str, client, permanent: bool):
        with pending_tasks_lock:
            task = pending_tasks.get(task_id, {})
        channel = task.get("channel")
        thread_ts = task.get("thread_ts")
        user_id = task.get("user_id")
        lang = get_user_lang(client, user_id) if user_id else "en"

        if channel and thread_ts:
            client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=get_msg("approved_running", lang))

        def on_response(text):
            if channel and thread_ts:
                blocks = build_message_with_delete_button(text)
                client.chat_postMessage(channel=channel, thread_ts=thread_ts, blocks=blocks, text=text)

        def on_images(paths):
            if client and channel and thread_ts:
                upload_images_to_slack(client, channel, thread_ts, paths, get_msg("image_generated", lang))

        core.execute_pending_task(
            task_id,
            permanent=permanent,
            lang=lang,
            on_response=on_response,
            on_images=on_images,
        )

    return SocketModeHandler(app, SLACK_APP_TOKEN)
