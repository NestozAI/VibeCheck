"""
VibeCheck Core - Transport-agnostic orchestration layer.
Used by both web_server.py (WebSocket) and slack_handler.py (Slack).
"""

import os
import re
import time
import uuid
import logging
import threading
from typing import Optional, Callable, List, Dict

from config import WORK_DIR, get_msg
from security import (
    add_trusted_path, remove_trusted_path, get_trusted_paths,
    check_untrusted_paths, is_safe_system_command,
    pending_tasks, pending_tasks_lock,
)
from claude_handler import ClaudeRunner
from image_handler import (
    get_images_with_mtime, find_new_or_modified_images,
    extract_image_paths_from_response, find_contextual_images,
)
from html_screenshot import html_file_to_screenshot
from cleaner import clean_output, clean_and_split

logger = logging.getLogger(__name__)

SCREENSHOT_KEYWORDS = [
    "screenshot", "capture", "show me", "preview", "ui",
]


class VibeCheckCore:
    """
    Stateful orchestration engine. One instance per application.

    All output goes through callbacks so transport layers
    (WebSocket, Slack) can deliver results their own way.
    """

    def __init__(self):
        self.claude_runner: Optional[ClaudeRunner] = None
        self.processing = False
        self._lock = threading.Lock()
        self._ensure_runner()

    def _ensure_runner(self):
        if not self.claude_runner:
            self.claude_runner = ClaudeRunner(WORK_DIR)

    def reset_session(self):
        self._ensure_runner()
        self.claude_runner.reset_session()

    # ------------------------------------------------------------------
    # Main message handler
    # ------------------------------------------------------------------

    def handle_message(
        self,
        message: str,
        lang: str = "en",
        on_thinking: Optional[Callable[[], None]] = None,
        on_response: Optional[Callable[[str], None]] = None,
        on_images: Optional[Callable[[List[str]], None]] = None,
        on_approval_required: Optional[Callable[[str, List[str], str], None]] = None,
    ) -> None:
        """Process a user message. Calls back into transport layer."""
        self._ensure_runner()
        msg_lower = message.lower().strip()

        # --- Commands ---
        if msg_lower in ["/reset", "reset"]:
            self.reset_session()
            if on_response:
                on_response("Session reset. Starting new conversation.")
            return

        if msg_lower in ["/help", "help"]:
            if on_response:
                on_response(self._help_text())
            return

        if msg_lower == "/paths":
            if on_response:
                on_response(self._format_paths())
            return

        if msg_lower.startswith("/trust "):
            path = message[7:].strip()
            if on_response:
                if path:
                    add_trusted_path(path)
                    on_response(f"Added to trusted paths: `{path}`")
                else:
                    on_response("Usage: `/trust /path/to/folder`")
            return

        # --- Busy guard ---
        if self.processing:
            if on_response:
                on_response("A previous task is still running. Please wait.")
            return

        # --- Security check ---
        untrusted_paths = check_untrusted_paths(message)
        if untrusted_paths and not is_safe_system_command(message):
            task_id = str(uuid.uuid4())[:8]
            with pending_tasks_lock:
                pending_tasks[task_id] = {
                    "message": message,
                    "untrusted_paths": untrusted_paths,
                    "timestamp": time.time(),
                }
            if on_approval_required:
                on_approval_required(task_id, untrusted_paths, message)
            return

        # --- Execute ---
        self._run_claude(message, lang, on_thinking, on_response, on_images)

    # ------------------------------------------------------------------
    # Execute a previously approved pending task
    # ------------------------------------------------------------------

    def execute_pending_task(
        self,
        task_id: str,
        permanent: bool = False,
        lang: str = "en",
        on_thinking: Optional[Callable[[], None]] = None,
        on_response: Optional[Callable[[str], None]] = None,
        on_images: Optional[Callable[[List[str]], None]] = None,
    ) -> None:
        with pending_tasks_lock:
            task = pending_tasks.pop(task_id, None)

        if not task:
            logger.warning(f"Task not found: {task_id}")
            if on_response:
                on_response("Task not found or already executed.")
            return

        if permanent:
            for p in task["untrusted_paths"]:
                add_trusted_path(p)

        self._run_claude(task["message"], lang, on_thinking, on_response, on_images)

    # ------------------------------------------------------------------
    # Internal: run Claude and deliver results via callbacks
    # ------------------------------------------------------------------

    def _run_claude(
        self,
        message: str,
        lang: str,
        on_thinking: Optional[Callable] = None,
        on_response: Optional[Callable[[str], None]] = None,
        on_images: Optional[Callable[[List[str]], None]] = None,
    ) -> None:
        self._ensure_runner()

        with self._lock:
            self.processing = True

        try:
            if on_thinking:
                on_thinking()

            before_images = get_images_with_mtime(WORK_DIR)

            response = self.claude_runner.run(message)

            # Clean and deliver text
            cleaned = clean_output(response)
            if cleaned and on_response:
                messages = clean_and_split(cleaned)
                combined = "\n\n".join(m for m in messages if m.strip())
                on_response(combined)
            elif on_response:
                on_response(get_msg("no_response", lang))

            # Collect and deliver images
            if on_images:
                images = self._collect_images(message, response, before_images)
                if images:
                    on_images(images)
        finally:
            with self._lock:
                self.processing = False

    # ------------------------------------------------------------------
    # Image collection (screenshots + new/modified + mentioned + contextual)
    # ------------------------------------------------------------------

    def _collect_images(
        self,
        user_msg: str,
        response: str,
        before_images: Dict[str, float],
    ) -> List[str]:
        collected: List[str] = []
        seen: set = set()

        def _add(paths: List[str]):
            for p in paths:
                if p not in seen:
                    seen.add(p)
                    collected.append(p)

        # 0. Screenshot HTML files if requested
        wants_screenshot = any(kw in user_msg.lower() for kw in SCREENSHOT_KEYWORDS)
        if wants_screenshot:
            html_matches = re.findall(r'([a-zA-Z0-9_\-./]+\.html)', response)
            for html_file in html_matches:
                html_path = html_file if html_file.startswith("/") else os.path.join(WORK_DIR, html_file)
                if os.path.isfile(html_path):
                    try:
                        screenshot_path = os.path.join(WORK_DIR, "screenshot.png")
                        html_file_to_screenshot(html_path, screenshot_path, width=1200, height=800, full_page=True)
                        _add([screenshot_path])
                        break
                    except Exception as e:
                        logger.error(f"Screenshot generation failed: {e}")

        # 1. New or modified images
        new_images = find_new_or_modified_images(WORK_DIR, before_images)
        _add(new_images)

        # 2. Images mentioned in response
        mentioned = extract_image_paths_from_response(response, WORK_DIR)
        _add(mentioned)

        # 3. Contextual images
        contextual = find_contextual_images(user_msg, response, WORK_DIR)
        _add(contextual)

        return collected

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _help_text() -> str:
        return (
            "**VibeCheck Help**\n\n"
            "**Usage:**\n"
            "- Send a message and Claude will respond\n"
            "- Conversations are automatically continued\n\n"
            "**Commands:**\n"
            "- `/reset` - Start new conversation\n"
            "- `/help` - This help\n"
            "- `/paths` - View trusted paths\n"
            "- `/trust /path` - Add path to trusted list\n\n"
            f"**Working Directory:** `{WORK_DIR}`"
        )

    @staticmethod
    def _format_paths() -> str:
        paths = get_trusted_paths()
        if not paths:
            return "No trusted paths registered."
        lines = ["**Trusted Paths:**"]
        for p in paths:
            lines.append(f"- `{p}`")
        return "\n".join(lines)
