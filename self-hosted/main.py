"""
Claude Code Bridge Bot
- Remotely control Claude Code CLI from Slack
- Run CLI via subprocess (--print mode)
- Maintain conversations with --continue
- Path-based security approval system
"""

import os
import re
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
from html_screenshot import html_file_to_screenshot
from ui_builder import (
    build_approval_blocks, build_message_with_delete_button,
    build_trusted_paths_blocks
)
from cleaner import clean_and_split, clean_output

# Logging setup (basicConfig already called in config)
logger = logging.getLogger(__name__)

# Initialize Slack app
app = App(token=SLACK_BOT_TOKEN)

# Global Claude runner
claude_runner: Optional[ClaudeRunner] = None


# =============================================================================
# Helper Functions
# =============================================================================

def extract_message_text(event: dict) -> str:
    """Extract message text after removing mentions"""
    text = event.get("text", "")
    import re
    text = re.sub(r'<@[A-Z0-9]+>', '', text).strip()
    return text


def process_and_reply(say, thread_ts: str, user_message: str, client=None, channel: str = None, user_id: str = None):
    """Run Claude and send response"""
    global claude_runner

    if not claude_runner:
        claude_runner = ClaudeRunner(WORK_DIR)

    # Get user language setting
    lang = get_user_lang(client, user_id) if client and user_id else "ko"

    # Handle special commands
    msg_lower = user_message.lower().strip()

    if msg_lower in ["/reset", "리셋", "새대화", "reset"]:
        claude_runner.reset_session()
        reset_msg = "🔄 Starting a new conversation!" if lang == "en" else "🔄 Starting a new conversation!"
        say(text=reset_msg, thread_ts=thread_ts)
        return

    if msg_lower in ["/help", "도움말", "help"]:
        say(text=(
            f"{get_msg('help_title', lang)}\n\n"
            + ("*Usage:*\n• Send a message and Claude will respond\n• Conversations are automatically continued\n\n"
               "*Commands:*\n• `reset` or `/reset` - Start new conversation\n• `help` or `/help` - This help\n"
               "• `/paths` - View trusted paths\n• `/trust /path` - Add path to trusted list\n\n"
               if lang == "en" else
               "*Usage:*\n• Send a message and Claude will respond\n• Conversations are automatically continued\n\n"
               "*Commands:*\n• `reset` or `/reset` - Start new conversation\n• `help` or `/help` - This help\n"
               "• `/paths` - View trusted paths\n• `/trust /path` - Add path to trusted list\n\n")
            + f"*{'Working Directory' if lang == 'en' else 'Working Directory'}:* `{WORK_DIR}`"
        ), thread_ts=thread_ts)
        return

    if msg_lower == "/paths" or msg_lower == "경로":
        blocks = build_trusted_paths_blocks()
        say(blocks=blocks, text="Trusted paths list", thread_ts=thread_ts)
        return

    if msg_lower.startswith("/trust "):
        path = user_message[7:].strip()
        if path:
            add_trusted_path(path)
            say(text=f"✅ Added to trusted paths: `{path}`", thread_ts=thread_ts)
        else:
            say(text="❌ Please enter a path. Example: `/trust /home/user/project`", thread_ts=thread_ts)
        return

    # Language setting command
    if msg_lower.startswith("/lang"):
        parts = msg_lower.split()
        if len(parts) == 2 and parts[1] in ["en", "ko"]:
            user_lang_override[user_id] = parts[1]
            if parts[1] == "en":
                say(text="✅ Language set to English", thread_ts=thread_ts)
            else:
                say(text="✅ Language set to Korean", thread_ts=thread_ts)
        else:
            say(text="Usage: `/lang en` or `/lang ko`", thread_ts=thread_ts)
        return

    # Security check: check for untrusted paths
    untrusted_paths = check_untrusted_paths(user_message)

    # Safe system commands pass through
    if untrusted_paths and not is_safe_system_command(user_message):
        # Approval required
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

        logger.info(f"🛡️ Awaiting approval: {task_id} - paths: {untrusted_paths}")

        blocks = build_approval_blocks(task_id, untrusted_paths, user_message)
        say(blocks=blocks, text="Security approval required", thread_ts=thread_ts)
        return

    # Processing message
    thinking_msg = say(text=get_msg("thinking", lang), thread_ts=thread_ts)

    # Save existing image list before running Claude (with modification times)
    before_images = get_images_with_mtime(WORK_DIR)

    # Run Claude
    response = claude_runner.run(user_message)

    # Delete "thinking" message
    if thinking_msg and client and channel:
        try:
            client.chat_delete(channel=channel, ts=thinking_msg.get("ts"))
        except Exception as e:
            logger.warning(f"Failed to delete thinking message: {e}")

    # Clean and send response
    cleaned = clean_output(response)
    if cleaned:
        # Split long messages
        messages = clean_and_split(cleaned)
        for msg in messages:
            if msg.strip():
                # Send message with delete button
                blocks = build_message_with_delete_button(msg)
                say(blocks=blocks, text=msg, thread_ts=thread_ts)
    else:
        say(text=get_msg("no_response", lang), thread_ts=thread_ts)

    # Handle image uploads
    if client and channel:
        uploaded_images = set()

        # 0. Detect screenshot request - Generate HTML file screenshot
        screenshot_keywords = ['스크린샷', 'screenshot', '캡처', 'capture', '보여줘', 'show me', 'preview', '미리보기']
        wants_screenshot = any(kw in user_message.lower() for kw in screenshot_keywords)

        if wants_screenshot:
            # Find HTML file paths in response
            html_pattern = r'([a-zA-Z0-9_\-./]+\.html)'
            html_matches = re.findall(html_pattern, response)

            for html_file in html_matches:
                # Handle absolute or relative paths
                if html_file.startswith('/'):
                    html_path = html_file
                else:
                    html_path = os.path.join(WORK_DIR, html_file)

                if os.path.isfile(html_path):
                    try:
                        screenshot_path = os.path.join(WORK_DIR, 'screenshot.png')
                        logger.info(f"Generating HTML screenshot: {html_path}")
                        html_file_to_screenshot(html_path, screenshot_path, width=1200, height=800, full_page=True)
                        logger.info(f"Screenshot generated: {screenshot_path}")

                        # Upload screenshot
                        upload_images_to_slack(client, channel, thread_ts, [screenshot_path],
                            "Screenshot", delete_after_upload=True)
                        uploaded_images.add(screenshot_path)
                        break  # Only process the first HTML file
                    except Exception as e:
                        logger.error(f"Screenshot generation failed: {e}")

        # 1. Upload newly created or modified images
        new_images = find_new_or_modified_images(WORK_DIR, before_images)
        new_images = [img for img in new_images if img not in uploaded_images]
        if new_images:
            logger.info(f"New/modified images found: {new_images}")
            upload_images_to_slack(client, channel, thread_ts, new_images, get_msg("image_generated", lang))
            uploaded_images.update(new_images)

        # 2. Upload existing images mentioned in response
        mentioned_images = extract_image_paths_from_response(response, WORK_DIR)
        # Exclude already uploaded images
        mentioned_images = [img for img in mentioned_images if img not in uploaded_images]
        if mentioned_images:
            logger.info(f"Images mentioned in response: {mentioned_images}")
            upload_images_to_slack(client, channel, thread_ts, mentioned_images, get_msg("image_referenced", lang))
            uploaded_images.update(mentioned_images)

        # 3. Find context-based images (e.g. "show me the graph")
        contextual_images = find_contextual_images(user_message, response, WORK_DIR)
        contextual_images = [img for img in contextual_images if img not in uploaded_images]
        if contextual_images:
            logger.info(f"Context-based images: {contextual_images}")
            upload_images_to_slack(client, channel, thread_ts, contextual_images, get_msg("image_related", lang))


def execute_pending_task(task_id: str, client, permanent: bool = False):
    """Execute a pending task"""
    global claude_runner

    with pending_tasks_lock:
        task = pending_tasks.pop(task_id, None)

    if not task:
        logger.warning(f"Task not found: {task_id}")
        return

    # Add paths if permanent approval
    if permanent:
        for path in task["untrusted_paths"]:
            add_trusted_path(path)

    channel = task["channel"]
    thread_ts = task["thread_ts"]
    user_message = task["message"]
    user_id = task.get("user_id")

    # User language setting
    lang = get_user_lang(client, user_id) if user_id else "ko"

    if not claude_runner:
        claude_runner = ClaudeRunner(WORK_DIR)

    # Execution notification
    client.chat_postMessage(
        channel=channel,
        thread_ts=thread_ts,
        text=get_msg("approved_running", lang)
    )

    # Save existing image list before running Claude (with modification times)
    before_images = get_images_with_mtime(WORK_DIR)

    # Run Claude
    response = claude_runner.run(user_message)

    # Clean and send response
    cleaned = clean_output(response)
    if cleaned:
        messages = clean_and_split(cleaned)
        for msg in messages:
            if msg.strip():
                # Send message with delete button
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

    # Handle image uploads
    uploaded_images = set()

    # 0. Detect screenshot request - Generate HTML file screenshot
    screenshot_keywords = ['스크린샷', 'screenshot', '캡처', 'capture', '보여줘', 'show me', 'preview', '미리보기']
    wants_screenshot = any(kw in user_message.lower() for kw in screenshot_keywords)

    if wants_screenshot:
        html_pattern = r'([a-zA-Z0-9_\-./]+\.html)'
        html_matches = re.findall(html_pattern, response)

        for html_file in html_matches:
            if html_file.startswith('/'):
                html_path = html_file
            else:
                html_path = os.path.join(WORK_DIR, html_file)

            if os.path.isfile(html_path):
                try:
                    screenshot_path = os.path.join(WORK_DIR, 'screenshot.png')
                    logger.info(f"Generating HTML screenshot: {html_path}")
                    html_file_to_screenshot(html_path, screenshot_path, width=1200, height=800, full_page=True)
                    logger.info(f"Screenshot generated: {screenshot_path}")

                    upload_images_to_slack(client, channel, thread_ts, [screenshot_path],
                        "Screenshot", delete_after_upload=True)
                    uploaded_images.add(screenshot_path)
                    break
                except Exception as e:
                    logger.error(f"Screenshot generation failed: {e}")

    # 1. Upload newly created or modified images
    new_images = find_new_or_modified_images(WORK_DIR, before_images)
    new_images = [img for img in new_images if img not in uploaded_images]
    if new_images:
        logger.info(f"New/modified images found: {new_images}")
        upload_images_to_slack(client, channel, thread_ts, new_images, get_msg("image_generated", lang))
        uploaded_images.update(new_images)

    # 2. Upload existing images mentioned in response
    mentioned_images = extract_image_paths_from_response(response, WORK_DIR)
    mentioned_images = [img for img in mentioned_images if img not in uploaded_images]
    if mentioned_images:
        logger.info(f"Images mentioned in response: {mentioned_images}")
        upload_images_to_slack(client, channel, thread_ts, mentioned_images, get_msg("image_referenced", lang))
        uploaded_images.update(mentioned_images)

    # 3. Find context-based images
    contextual_images = find_contextual_images(user_message, response, WORK_DIR)
    contextual_images = [img for img in contextual_images if img not in uploaded_images]
    if contextual_images:
        logger.info(f"Context-based images: {contextual_images}")
        upload_images_to_slack(client, channel, thread_ts, contextual_images, get_msg("image_related", lang))


# =============================================================================
# Slack event handlers
# =============================================================================

@app.event("app_mention")
def handle_mention(event, say, client):
    """Handle bot mentions"""
    logger.info(f"Mention received: {event}")

    user_message = extract_message_text(event)
    thread_ts = event.get("thread_ts", event.get("ts"))
    channel = event.get("channel")
    user_id = event.get("user")

    if not user_message:
        say(text="How can I help you? 🤔", thread_ts=thread_ts)
        return

    process_and_reply(say, thread_ts, user_message, client=client, channel=channel, user_id=user_id)


@app.event("message")
def handle_message(event, say, client):
    """Handle DM messages"""
    # Ignore bot's own messages
    if event.get("bot_id"):
        return

    # Only handle DMs
    if event.get("channel_type") != "im":
        return

    logger.info(f"DM received: {event}")

    user_message = event.get("text", "").strip()
    if not user_message:
        return

    thread_ts = event.get("thread_ts", event.get("ts"))
    channel = event.get("channel")
    user_id = event.get("user")

    process_and_reply(say, thread_ts, user_message, client=client, channel=channel, user_id=user_id)


# =============================================================================
# Button action handlers
# =============================================================================

@app.action("approve_access")
def handle_approve_access(ack, body, client):
    """One-time approval"""
    ack()

    task_id = body["actions"][0]["value"]
    user = body["user"]["username"]

    logger.info(f"✅ Approved (one-time): {task_id} by {user}")

    # Update button message
    client.chat_update(
        channel=body["channel"]["id"],
        ts=body["message"]["ts"],
        text=f"✅ Approved (one-time) by @{user}",
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"✅ *Approved* (one-time) by @{user}"}
            }
        ]
    )

    # Execute task
    execute_pending_task(task_id, client, permanent=False)


@app.action("approve_permanent")
def handle_approve_permanent(ack, body, client):
    """Permanent approval (add path)"""
    ack()

    task_id = body["actions"][0]["value"]
    user = body["user"]["username"]

    logger.info(f"✅ Approved (permanent): {task_id} by {user}")

    # Update button message
    client.chat_update(
        channel=body["channel"]["id"],
        ts=body["message"]["ts"],
        text=f"✅ Approved (permanent) by @{user}",
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"✅ *Approved* (permanent - added to trusted paths) by @{user}"}
            }
        ]
    )

    # Execute task (permanent approval)
    execute_pending_task(task_id, client, permanent=True)


@app.action("deny_access")
def handle_deny_access(ack, body, client):
    """Deny access"""
    ack()

    task_id = body["actions"][0]["value"]
    user = body["user"]["username"]

    logger.info(f"❌ Denied: {task_id} by {user}")

    # Remove pending task
    with pending_tasks_lock:
        pending_tasks.pop(task_id, None)

    # Update button message
    client.chat_update(
        channel=body["channel"]["id"],
        ts=body["message"]["ts"],
        text=f"❌ Denied by @{user}",
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"❌ *Denied* by @{user}"}
            }
        ]
    )


@app.action("remove_trusted_path")
def handle_remove_trusted_path(ack, body, client):
    """Remove trusted path"""
    ack()

    path = body["actions"][0]["value"]
    user = body["user"]["username"]

    if remove_trusted_path(path):
        logger.info(f"🗑️ Path removed: {path} by {user}")

        # Show updated list
        blocks = build_trusted_paths_blocks()
        client.chat_update(
            channel=body["channel"]["id"],
            ts=body["message"]["ts"],
            text="Trusted paths list",
            blocks=blocks
        )
    else:
        client.chat_postMessage(
            channel=body["channel"]["id"],
            text=f"❌ Cannot remove the default path: `{path}`"
        )


@app.action("delete_message")
def handle_delete_message(ack, body, client):
    """Delete message"""
    ack()

    channel = body["channel"]["id"]
    message_ts = body["message"]["ts"]
    user = body["user"]["username"]

    try:
        client.chat_delete(channel=channel, ts=message_ts)
        logger.info(f"🗑️ Message deleted: {message_ts} by {user}")
    except Exception as e:
        logger.error(f"Message deletion failed: {e}")
        # Notify user on deletion failure
        try:
            client.chat_postEphemeral(
                channel=channel,
                user=body["user"]["id"],
                text=f"❌ Failed to delete message: {str(e)}"
            )
        except:
            pass


@app.event("app_home_opened")
def handle_app_home(event, client):
    """App home tab"""
    user_id = event["user"]

    session_status = "✅ Conversation in progress" if (claude_runner and claude_runner.session_started) else "🆕 New conversation"
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
                        "text": "Remotely control the Claude Code CLI on your local server from Slack."
                    }
                },
                {
                    "type": "divider"
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Session status:* {session_status}\n*Working directory:* `{WORK_DIR}`\n*Trusted paths:* {trusted_count}"
                    }
                },
                {
                    "type": "divider"
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Usage:*\n"
                               "• Send a DM and Claude will respond\n"
                               "• Mention `@bot message` in a channel\n"
                               "• Conversations are automatically continued with `--continue`\n\n"
                               "*Commands:*\n"
                               "• `reset` - Start new conversation\n"
                               "• `help` - Show help\n"
                               "• `/paths` - Trusted paths list\n"
                               "• `/trust /path` - Add trusted path\n\n"
                               "*🛡️ Security:*\n"
                               "• Approval required when accessing untrusted paths\n"
                               "• System monitoring commands are auto-allowed"
                    }
                }
            ]
        }
    )


# =============================================================================
# Main
# =============================================================================

def main():
    """Main function"""
    global claude_runner

    logger.info("=" * 50)
    logger.info("🚀 Claude Code Bridge Bot starting!")
    logger.info(f"📂 Working directory: {WORK_DIR}")
    logger.info(f"🔐 Trusted paths: {get_trusted_paths()}")
    logger.info("=" * 50)

    # Initialize Claude runner
    claude_runner = ClaudeRunner(WORK_DIR)
    logger.info("✅ Claude runner ready")

    # Start Slack handler
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)

    try:
        logger.info("⚡️ Connecting to Slack...")
        handler.start()
    except KeyboardInterrupt:
        logger.info("Shutdown signal received")
    finally:
        logger.info("👋 Bridge Bot shutting down")


if __name__ == "__main__":
    main()
