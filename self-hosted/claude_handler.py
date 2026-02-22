
import os
import subprocess
import threading
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# Claude Runner
# =============================================================================

class ClaudeRunner:
    """
    Run Claude CLI via subprocess.

    Execute in --print mode and return results.
    Continue previous conversations with --continue.
    """

    def __init__(self, work_dir: str):
        self.work_dir = work_dir
        self.session_started = False  # True after first message
        self.lock = threading.Lock()

    def run(self, message: str, continue_session: bool = True) -> str:
        """
        Send a message to Claude and receive a response.

        Args:
            message: User message
            continue_session: If True, continue previous conversation with --continue

        Returns:
            Claude's response text
        """
        with self.lock:
            # Base command
            cmd = [
                "claude",
                "--print",  # non-interactive mode
                "--dangerously-skip-permissions",  # skip permission prompts
            ]

            # Add --continue if not the first message
            if continue_session and self.session_started:
                cmd.append("--continue")

            # Add message
            cmd.append(message)

            logger.info(f"Running Claude: {' '.join(cmd[:4])}... '{message[:50]}...'")

            try:
                # Run subprocess
                result = subprocess.run(
                    cmd,
                    cwd=self.work_dir,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout
                    env={**os.environ, 'NO_COLOR': '1'}
                )

                # Mark session as started after first successful message
                if not self.session_started:
                    self.session_started = True

                # Combine stdout and stderr
                output = result.stdout
                if result.stderr:
                    logger.warning(f"Claude stderr: {result.stderr[:200]}")

                if result.returncode != 0:
                    logger.error(f"Claude execution failed (code {result.returncode}): {result.stderr}")
                    return f"❌ Claude error: {result.stderr or 'Unknown error'}"

                logger.info(f"Claude response ({len(output)} chars): {output[:100]}...")
                return output

            except subprocess.TimeoutExpired:
                logger.error("Claude timeout (5 minutes)")
                return "❌ Claude response timeout (exceeded 5 minutes)"
            except Exception as e:
                logger.error(f"Claude execution error: {e}")
                return f"❌ Claude execution error: {str(e)}"

    def reset_session(self):
        """Reset session (start new conversation)"""
        with self.lock:
            self.session_started = False
            logger.info("Claude session reset")
