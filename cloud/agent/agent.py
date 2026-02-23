#!/usr/bin/env python3
"""
VibeCheck Agent
- WebSocket connection to central server
- Execute CLI locally
- Send results to server
- Image detection and upload
- Path-based security system
- PTY mode: view terminal UI directly on the web
"""

import os
import sys
import asyncio
import argparse
import subprocess
import logging
import json
import re
import glob
import base64
# PTY-related imports removed (switched to Message mode)
from typing import Optional, Set, List, Dict
from concurrent.futures import ThreadPoolExecutor

import websockets
from websockets.exceptions import ConnectionClosed

try:
    from html_screenshot import html_file_to_screenshot, screenshot_project, detect_project_type
    HAS_SCREENSHOT = True
except ImportError as e:
    HAS_SCREENSHOT = False
    print(f"⚠️ Screenshot feature disabled: {e}")
except Exception as e:
    HAS_SCREENSHOT = False
    print(f"⚠️ Screenshot feature disabled (other error): {e}")

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

# Railway deployment URL
DEFAULT_SERVER = "wss://vibecheck.sotaaz.com/ws/agent"

# Session file storage directory
SESSION_DIR = os.path.expanduser("~/.vibecheck")

# Thread pool for CLI execution
executor = ThreadPoolExecutor(max_workers=1)

# Image extensions
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}

# Safe system commands (can be executed without approval)
SAFE_SYSTEM_COMMANDS = {
    'nvidia-smi', 'df', 'free', 'uptime', 'whoami', 'hostname',
    'cat /proc/cpuinfo', 'cat /proc/meminfo', 'ps', 'top -bn1',
    'ls', 'pwd', 'date', 'which', 'echo', 'git status', 'git log', 'git diff'
}


# =============================================================================
# Image detection utilities
# =============================================================================

def get_images_with_mtime(work_dir: str, max_depth: int = 2) -> Dict[str, float]:
    """Return image files and modification times in work directory (performance optimized)"""
    images = {}
    # Directories to exclude (performance)
    SKIP_DIRS = {'node_modules', '.git', '__pycache__', 'venv', '.venv', 'dist', 'build', '.next'}

    try:
        for root, dirs, files in os.walk(work_dir):
            # Depth limit
            depth = root[len(work_dir):].count(os.sep)
            if depth >= max_depth:
                dirs[:] = []  # Stop deeper traversal
                continue

            # Skip excluded directories
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in IMAGE_EXTENSIONS:
                    path = os.path.join(root, f)
                    try:
                        images[path] = os.path.getmtime(path)
                    except OSError:
                        pass
    except Exception as e:
        logger.warning(f"Image scan error: {e}")

    return images


def find_new_or_modified_images(work_dir: str, before_images: Dict[str, float], max_depth: int = 2) -> List[str]:
    """Find newly created or modified image files"""
    after_images = get_images_with_mtime(work_dir, max_depth)
    result = []
    for path, mtime in after_images.items():
        if path not in before_images or mtime > before_images[path]:
            result.append(path)
    return result


def image_to_base64(image_path: str) -> Optional[str]:
    """Encode image file to base64"""
    try:
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except Exception as e:
        logger.error(f"Image encoding failed: {e}")
        return None


# =============================================================================
# Path security utilities
# =============================================================================

def normalize_path(path: str) -> str:
    """Normalize path"""
    return os.path.normpath(os.path.abspath(os.path.expanduser(path)))


def extract_paths_from_message(message: str) -> List[str]:
    """Extract paths from message"""
    paths = []

    # Absolute path pattern (starts with /)
    abs_pattern = r'(/[a-zA-Z0-9_\-./]+)'
    abs_matches = re.findall(abs_pattern, message)
    paths.extend(abs_matches)

    # Relative path pattern (starts with ./ or ../)
    rel_pattern = r'(\.\./[a-zA-Z0-9_\-./]+|\.\/[a-zA-Z0-9_\-./]+)'
    rel_matches = re.findall(rel_pattern, message)
    paths.extend(rel_matches)

    # Remove duplicates
    unique_paths = []
    seen = set()
    for p in paths:
        if p.startswith('.') and '/' not in p:
            continue
        normalized = normalize_path(p) if p.startswith('/') else p
        if normalized not in seen:
            seen.add(normalized)
            unique_paths.append(p)

    return unique_paths


def is_safe_system_command(message: str) -> bool:
    """Check if it is a safe system command"""
    msg_lower = message.lower().strip()
    for cmd in SAFE_SYSTEM_COMMANDS:
        if cmd in msg_lower:
            return True
    return False


# =============================================================================
# Session ID management
# =============================================================================

def get_session_file_path(work_dir: str) -> str:
    """Return session file path for the work directory"""
    # Hash the directory path to generate a unique filename
    import hashlib
    dir_hash = hashlib.md5(work_dir.encode()).hexdigest()[:12]
    return os.path.join(SESSION_DIR, f"session_{dir_hash}.json")


def save_session_id(work_dir: str, session_id: str):
    """Save session ID"""
    os.makedirs(SESSION_DIR, exist_ok=True)
    session_file = get_session_file_path(work_dir)
    data = {
        "work_dir": work_dir,
        "session_id": session_id,
        "updated_at": str(os.popen("date -Iseconds").read().strip())
    }
    try:
        with open(session_file, 'w') as f:
            json.dump(data, f)
        logger.info(f"Session ID saved: {session_id[:20]}...")
    except Exception as e:
        logger.warning(f"Failed to save session ID: {e}")


def load_session_id(work_dir: str) -> Optional[str]:
    """Load saved session ID"""
    session_file = get_session_file_path(work_dir)
    if os.path.exists(session_file):
        try:
            with open(session_file, 'r') as f:
                data = json.load(f)
                session_id = data.get("session_id")
                if session_id:
                    logger.info(f"Previous session ID loaded: {session_id[:20]}...")
                    return session_id
        except Exception as e:
            logger.warning(f"Failed to load session ID: {e}")
    return None


def clear_session_id(work_dir: str):
    """Delete session ID (when starting a new session)"""
    session_file = get_session_file_path(work_dir)
    if os.path.exists(session_file):
        try:
            os.remove(session_file)
            logger.info("Previous session ID deleted")
        except Exception as e:
            logger.warning(f"Failed to delete session ID: {e}")


class VibeAgent:
    """VibeCheck Agent"""

    def __init__(self, api_key: str, work_dir: str, server_url: str = DEFAULT_SERVER, new_session: bool = False):
        self.api_key = api_key
        self.work_dir = work_dir
        self.server_url = f"{server_url}?key={api_key}"
        self.session_started = False
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.processing = False  # CLI execution in progress flag

        # Trusted paths (work directory is trusted by default)
        self.trusted_paths: Set[str] = {normalize_path(work_dir)}

        # Pending approval request
        self.pending_approval: Optional[dict] = None

        # Store recently worked project path (used for screenshots, etc.)
        self.last_project_path: Optional[str] = None

        # Session ID management
        self.session_id: Optional[str] = None
        if new_session:
            clear_session_id(work_dir)
        else:
            self.session_id = load_session_id(work_dir)

        # Currently running process (for interrupt)
        self.current_process: Optional[subprocess.Popen] = None
        self.process_interrupted = False

    def is_path_trusted(self, path: str) -> bool:
        """Check if path is trusted"""
        normalized = normalize_path(path)
        for trusted in self.trusted_paths:
            if normalized == trusted or normalized.startswith(trusted + os.sep):
                return True
        return False

    def check_untrusted_paths(self, message: str) -> List[str]:
        """Find untrusted paths in message"""
        paths = extract_paths_from_message(message)
        untrusted = []
        for path in paths:
            if path.startswith('/'):
                if not self.is_path_trusted(path):
                    untrusted.append(path)
        return untrusted

    def add_trusted_path(self, path: str):
        """Add trusted path"""
        normalized = normalize_path(path)
        self.trusted_paths.add(normalized)
        logger.info(f"Trusted path added: {normalized}")

    def run_command_sync(self, message: str) -> str:
        """Execute CLI command locally (sync, runs in thread) - Popen-based with interrupt support"""
        cmd = [
            "claude",
            "--print",
            "--dangerously-skip-permissions",
        ]

        # Resume session: use --resume if saved session ID exists, otherwise --continue
        if self.session_id:
            cmd.extend(["--resume", self.session_id])
        elif self.session_started:
            cmd.append("--continue")

        cmd.append(message)

        logger.info(f"Executing command: {' '.join(cmd[:4])}...")

        # shell=True needed on Windows (npm global package PATH issue)
        use_shell = sys.platform == "win32"
        self.process_interrupted = False

        try:
            # Start process with Popen (interruptible)
            self.current_process = subprocess.Popen(
                cmd if not use_shell else " ".join(f'"{c}"' if ' ' in c else c for c in cmd),
                cwd=self.work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, 'NO_COLOR': '1'},
                shell=use_shell,
                encoding='utf-8',
                errors='replace'
            )

            # Wait for process completion (5 minute timeout)
            try:
                stdout, stderr = self.current_process.communicate(timeout=300)
            except subprocess.TimeoutExpired:
                self.current_process.kill()
                self.current_process.communicate()
                self.current_process = None
                return "Timeout (exceeded 5 minutes)"

            returncode = self.current_process.returncode
            self.current_process = None

            # Return special message if interrupted
            if self.process_interrupted:
                logger.info("Process was interrupted")
                return "⏹️ Task has been stopped. Waiting for next message..."

            if not self.session_started:
                self.session_started = True

            output = stdout
            if stderr:
                logger.warning(f"stderr: {stderr[:200]}")

            if returncode != 0:
                logger.error(f"CLI failed: returncode={returncode}, stderr={stderr[:200] if stderr else 'None'}, stdout={stdout[:200] if stdout else 'None'}")
                error_msg = stderr or stdout or 'Unknown error'

                # Start new session if session ID is invalid
                if self.session_id and ("session" in error_msg.lower() or "not found" in error_msg.lower()):
                    logger.warning("Session ID is invalid. Retrying with new session...")
                    self.session_id = None
                    clear_session_id(self.work_dir)
                    return self.run_command_sync(message)

                return f"Error: {error_msg}"

            # Extract and save session ID after first execution
            if not self.session_id:
                self._extract_and_save_session_id()

            logger.info(f"Response ({len(output)} chars): {output[:100]}...")
            return output

        except Exception as e:
            self.current_process = None
            logger.error(f"Execution error: {e}")
            return f"Execution error: {str(e)}"

    def interrupt_current_process(self):
        """Interrupt the currently running process"""
        if self.current_process:
            try:
                self.process_interrupted = True
                self.current_process.terminate()  # Send SIGTERM
                logger.info("Sent SIGTERM to process")
                # Wait 1 second, force kill if still alive
                try:
                    self.current_process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.current_process.kill()  # SIGKILL
                    logger.info("Sent SIGKILL to process")
                return True
            except Exception as e:
                logger.error(f"Failed to interrupt process: {e}")
                return False
        return False

    def _extract_and_save_session_id(self):
        """Extract and save Claude Code's latest session ID (directly from project directory)"""
        try:
            # Calculate Claude Code project directory path
            # ~/.claude/projects/-disk1-lecture-sotaaz-test-VibeCheck/
            work_dir_escaped = self.work_dir.replace('/', '-').lstrip('-')
            claude_project_dir = os.path.expanduser(f"~/.claude/projects/-{work_dir_escaped}")

            if not os.path.isdir(claude_project_dir):
                logger.debug(f"Claude project directory not found: {claude_project_dir}")
                return

            # Find the most recently modified .jsonl file
            jsonl_files = glob.glob(os.path.join(claude_project_dir, "*.jsonl"))
            if not jsonl_files:
                logger.debug("No session files found")
                return

            # Sort by modification time
            latest_file = max(jsonl_files, key=os.path.getmtime)
            session_id = os.path.basename(latest_file).replace('.jsonl', '')

            # Simple UUID format validation
            if len(session_id) == 36 and session_id.count('-') == 4:
                self.session_id = session_id
                save_session_id(self.work_dir, session_id)
                logger.info(f"Session ID extracted successfully: {session_id[:20]}...")
            else:
                logger.debug(f"Invalid session ID format: {session_id}")
        except Exception as e:
            logger.debug(f"Failed to extract session ID (ignored): {e}")

    async def run_command(self, message: str) -> str:
        """Execute CLI command (async wrapper)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, self.run_command_sync, message)

    def is_ws_open(self) -> bool:
        """Check WebSocket connection status (websockets 12.0+ compatible)"""
        if not self.ws:
            return False
        try:
            # Use state attribute in websockets 12.0+
            from websockets.protocol import State
            return self.ws.state == State.OPEN
        except (AttributeError, ImportError):
            # Backward compatibility
            try:
                return not self.ws.closed
            except AttributeError:
                return True  # Assume open if unable to check

    async def ping_loop(self):
        """Periodically send ping (keep connection alive)"""
        while True:
            try:
                await asyncio.sleep(15)  # Ping every 15 seconds
                if self.is_ws_open():
                    await self.ws.send(json.dumps({"type": "ping"}))
                    logger.debug("Ping sent")
            except ConnectionClosed:
                logger.debug("Connection closed during ping")
                break
            except Exception as e:
                logger.debug(f"Ping error: {e}")
                break

    async def sync_session_with_server(self):
        """Sync session ID with server (cross-device session sharing)"""
        if not self.is_ws_open():
            return

        try:
            # Send session sync request to server
            await self.ws.send(json.dumps({
                "type": "session_sync",
                "work_dir": self.work_dir,
                "session_id": self.session_id  # Send if available locally, None otherwise
            }))

            # Wait for server response (5 second timeout)
            import asyncio
            try:
                response = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
                data = json.loads(response)

                if data.get("type") == "session_info":
                    server_session_id = data.get("session_id")
                    source = data.get("source")

                    if server_session_id and source == "server":
                        # Existing session found on server -> use it
                        self.session_id = server_session_id
                        save_session_id(self.work_dir, server_session_id)
                        logger.info(f"Session ID synced from server: {server_session_id[:20]}...")
                    elif source == "agent":
                        # Agent's session saved to server
                        logger.info(f"Session ID saved to server: {self.session_id[:20] if self.session_id else 'None'}...")
                    else:
                        # No session - starting fresh
                        logger.info("No session found, starting new session")

            except asyncio.TimeoutError:
                logger.warning("Session sync timeout, using local session")

        except Exception as e:
            logger.warning(f"Session sync failed: {e}")

    async def update_session_on_server(self, session_id: str):
        """Update new session ID on server"""
        if not self.is_ws_open():
            return

        try:
            await self.ws.send(json.dumps({
                "type": "session_update",
                "work_dir": self.work_dir,
                "session_id": session_id
            }))
            logger.info(f"Session ID updated on server: {session_id[:20]}...")
        except Exception as e:
            logger.warning(f"Session update failed: {e}")

    async def connect(self):
        """Connect to server and process messages"""
        logger.info(f"Connecting to server: {self.server_url[:50]}...")

        try:
            async with websockets.connect(
                self.server_url,
                ping_interval=20,  # websockets library built-in ping
                ping_timeout=30
            ) as ws:
                self.ws = ws
                logger.info("Server connection successful!")

                # Wait for connection confirmation message
                response = await ws.recv()
                logger.info(f"Server response: {response}")

                # Sync session with server
                await self.sync_session_with_server()

                print("\n" + "=" * 50)
                print("  VibeCheck Agent running")
                print(f"  Work directory: {self.work_dir}")
                if self.session_id:
                    print(f"  Session ID: {self.session_id[:20]}...")
                print(f"  Screenshot feature: {'✅ Enabled' if HAS_SCREENSHOT else '❌ Disabled'}")
                print("  Send a message from Slack!")
                print("  Exit: Ctrl+C")
                print("=" * 50 + "\n")

                # Start ping loop
                ping_task = asyncio.create_task(self.ping_loop())

                try:
                    # Wait for incoming messages
                    async for message in ws:
                        await self.handle_message(message)
                finally:
                    ping_task.cancel()

        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"Server connection closed: {e}")
        except Exception as e:
            logger.error(f"Connection error: {e}")
            raise

    async def handle_message(self, raw_message: str):
        """Process messages received from server"""
        data = json.loads(raw_message)
        msg_type = data.get("type")

        if msg_type == "query":
            # Process user query
            message = data.get("message", "")
            logger.info(f"Query received: {message[:50]}...")

            # 🛡️ Security check: verify untrusted paths
            untrusted_paths = self.check_untrusted_paths(message)

            if untrusted_paths and not is_safe_system_command(message):
                # Approval needed - send approval request to server
                logger.info(f"Approval required: {untrusted_paths}")
                self.pending_approval = {"message": message, "paths": untrusted_paths}

                if self.is_ws_open():
                    await self.ws.send(json.dumps({
                        "type": "approval_required",
                        "paths": untrusted_paths,
                        "message": message[:200]  # Preview
                    }))
                return

            # Execute CLI
            logger.info("CLI execution starting...")
            await self.execute_and_respond(message)
            logger.info("CLI execution complete")

        elif msg_type == "approval":
            # Approval/rejection response from server
            approved = data.get("approved", False)
            permanent = data.get("permanent", False)

            if self.pending_approval:
                if approved:
                    logger.info("Approved! Executing command...")

                    # Add path if permanently approved
                    if permanent:
                        for path in self.pending_approval.get("paths", []):
                            self.add_trusted_path(path)

                    # Execute
                    await self.execute_and_respond(self.pending_approval["message"])
                else:
                    logger.info("Rejected")
                    if self.is_ws_open():
                        await self.ws.send(json.dumps({
                            "type": "response",
                            "result": "❌ Request was rejected."
                        }))

                self.pending_approval = None

        elif msg_type == "add_trusted_path":
            # Trusted path addition request from server
            path = data.get("path")
            if path:
                self.add_trusted_path(path)

        elif msg_type == "interrupt":
            # User clicked Stop button - interrupt current process
            logger.info("Interrupt request received")
            if self.processing and self.current_process:
                interrupted = self.interrupt_current_process()
                if interrupted and self.is_ws_open():
                    await self.ws.send(json.dumps({
                        "type": "response",
                        "result": "⏹️ Task has been stopped. Please enter a new message."
                    }))
            else:
                logger.info("No process to interrupt")

        elif msg_type == "ping":
            await self.ws.send(json.dumps({"type": "pong"}))

        elif msg_type == "pong":
            pass  # Server's pong response

        elif msg_type == "error":
            logger.error(f"Server error: {data.get('message')}")

    async def execute_and_respond(self, message: str):
        """Execute CLI and respond (with image detection)"""
        logger.info("Entering execute_and_respond")
        self.processing = True

        # Save image list before execution (async, 2 second timeout)
        before_images = {}
        try:
            loop = asyncio.get_event_loop()
            before_images = await asyncio.wait_for(
                loop.run_in_executor(None, get_images_with_mtime, self.work_dir),
                timeout=2.0
            )
            logger.debug(f"Image scan complete: {len(before_images)} files")
        except asyncio.TimeoutError:
            logger.warning("Image scan timeout (2s), skipping")
        except Exception as e:
            logger.warning(f"Image scan error: {e}")

        # Execute CLI (async - ping loop continues running)
        logger.info("Before run_command call...")
        old_session_id = self.session_id
        result = await self.run_command(message)
        logger.info(f"run_command complete: {len(result) if result else 0} chars")

        # Update server if new session ID was created
        if self.session_id and self.session_id != old_session_id:
            await self.update_session_on_server(self.session_id)

        self.processing = False

        # Extract and save project path from message (for screenshots)
        path_pattern = r'(/[a-zA-Z0-9_\-./]+)'
        path_matches = re.findall(path_pattern, message)
        for path in path_matches:
            if os.path.isdir(path):
                # Save if it's a directory (regardless of project type)
                self.last_project_path = path
                logger.info(f"Project path saved: {path}")
                break

        # Detect screenshot request and generate project screenshot
        screenshot_keywords = ['screenshot', 'capture', 'show me', 'preview', 'ui']
        wants_screenshot = any(kw in message.lower() for kw in screenshot_keywords)
        generated_screenshot = None  # Generated screenshot path

        if wants_screenshot and HAS_SCREENSHOT:
            project_dir = None
            # Save screenshots to /tmp (avoid permission issues)
            screenshot_path = '/tmp/vibecheck_screenshot.png'

            # 1. Extract project path from message
            for path in path_matches:
                if os.path.isdir(path):
                    # Check if it's a project directory
                    project_info = detect_project_type(path)
                    if project_info["type"] != "unknown":
                        project_dir = path
                        logger.info(f"Project detected: {path} -> {project_info}")
                        break

            # 2. Use saved project path (previous conversation context)
            if not project_dir and self.last_project_path and os.path.isdir(self.last_project_path):
                project_dir = self.last_project_path
                logger.info(f"Using saved project path: {project_dir}")

            # 3. Check work_dir
            if not project_dir:
                project_info = detect_project_type(self.work_dir)
                if project_info["type"] != "unknown":
                    project_dir = self.work_dir

            # 4. Find HTML file path in response (fallback)
            if not project_dir:
                html_pattern = r'([a-zA-Z0-9_\-./]+\.html)'
                html_matches = re.findall(html_pattern, result)
                for html_file in html_matches:
                    if html_file.startswith('/'):
                        html_path = html_file
                    else:
                        html_path = os.path.join(self.work_dir, html_file)
                    if os.path.isfile(html_path):
                        try:
                            logger.info(f"Generating screenshot for HTML file: {html_path}")
                            loop = asyncio.get_event_loop()
                            await loop.run_in_executor(
                                executor,
                                lambda hp=html_path: html_file_to_screenshot(hp, screenshot_path, width=1200, height=800, full_page=True)
                            )
                            logger.info(f"Screenshot generated: {screenshot_path}")
                            generated_screenshot = screenshot_path
                        except Exception as e:
                            logger.error(f"Screenshot generation failed: {e}")
                        break

            # Generate project screenshot (runs in separate thread - Playwright Sync API is incompatible with asyncio)
            if project_dir:
                try:
                    logger.info(f"Generating project screenshot: {project_dir}")
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        executor,
                        lambda: screenshot_project(project_dir, screenshot_path, width=1200, height=800, full_page=True)
                    )
                    logger.info(f"Screenshot generated: {screenshot_path}")
                    generated_screenshot = screenshot_path
                except Exception as e:
                    logger.error(f"Project screenshot generation failed: {e}")

        # Detect newly created images
        new_images = find_new_or_modified_images(self.work_dir, before_images)
        images_data = []

        # Add explicitly generated screenshot first
        if generated_screenshot and os.path.isfile(generated_screenshot):
            b64 = image_to_base64(generated_screenshot)
            if b64:
                images_data.append({
                    "filename": "screenshot.png",
                    "data": b64
                })
                logger.info(f"Screenshot image added: screenshot.png")
                # Delete screenshot file (temporary file)
                try:
                    os.remove(generated_screenshot)
                    logger.info("Screenshot file deleted")
                except:
                    pass

        for img_path in new_images[:5]:  # Maximum 5
            # Skip already added screenshots
            if generated_screenshot and img_path == generated_screenshot:
                continue
            b64 = image_to_base64(img_path)
            if b64:
                images_data.append({
                    "filename": os.path.basename(img_path),
                    "data": b64
                })
                logger.info(f"Image detected: {os.path.basename(img_path)}")

        # Image delivery request keywords
        image_request_keywords = ['image', 'send', 'attach']
        wants_image = any(kw in message.lower() for kw in image_request_keywords)

        # Extract and send image paths mentioned in response
        if not images_data or wants_image:  # If no images or explicit request
            # 1. Absolute path pattern
            img_path_pattern = r'(/[a-zA-Z0-9_\-./]+\.(?:png|jpg|jpeg|gif|webp|bmp))'
            mentioned_images = re.findall(img_path_pattern, result, re.IGNORECASE)

            # Also extract image paths from message
            msg_images = re.findall(img_path_pattern, message, re.IGNORECASE)
            mentioned_images = mentioned_images + msg_images

            # 2. Filename only case (e.g., 01-hero.png)
            filename_pattern = r'[\s\-]([a-zA-Z0-9_\-]+\.(?:png|jpg|jpeg|gif|webp|bmp))'
            mentioned_filenames = re.findall(filename_pattern, result, re.IGNORECASE)

            added_paths = set()

            # Process absolute path images
            for img_path in mentioned_images[:10]:
                if img_path in added_paths:
                    continue
                if os.path.isfile(img_path):
                    b64 = image_to_base64(img_path)
                    if b64:
                        images_data.append({
                            "filename": os.path.basename(img_path),
                            "data": b64
                        })
                        added_paths.add(img_path)
                        logger.info(f"Image extracted from response: {os.path.basename(img_path)}")

            # Filename only case - search in last_project_path
            if len(images_data) < 10 and self.last_project_path:
                search_dirs = [
                    self.last_project_path,
                    os.path.join(self.last_project_path, 'screenshots'),
                    os.path.join(self.last_project_path, 'images'),
                    os.path.join(self.last_project_path, 'assets'),
                ]
                for filename in mentioned_filenames[:10]:
                    if len(images_data) >= 10:
                        break
                    for search_dir in search_dirs:
                        if not os.path.isdir(search_dir):
                            continue
                        img_path = os.path.join(search_dir, filename)
                        if img_path in added_paths:
                            continue
                        if os.path.isfile(img_path):
                            b64 = image_to_base64(img_path)
                            if b64:
                                images_data.append({
                                    "filename": filename,
                                    "data": b64
                                })
                                added_paths.add(img_path)
                                logger.info(f"Image found in project folder: {filename}")
                            break

        # Send result
        if self.is_ws_open():
            try:
                response_data = {
                    "type": "response",
                    "result": result
                }

                # Include images if available
                if images_data:
                    response_data["images"] = images_data
                    logger.info(f"Sending {len(images_data)} images")

                await self.ws.send(json.dumps(response_data))
                logger.info("Response sent")
            except ConnectionClosed:
                logger.error("Connection closed while sending response")
        else:
            logger.error("Failed to send response: WebSocket is closed")


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="VibeCheck Agent")
    parser.add_argument("--key", "-k", required=True, help="API Key")
    parser.add_argument("--dir", "-d", default=os.getcwd(), help="Work directory")
    parser.add_argument("--server", "-s", default=DEFAULT_SERVER, help="Server URL")
    parser.add_argument("--new-session", "-n", action="store_true", help="Start new session (ignore previous session)")

    args = parser.parse_args()

    # Verify work directory
    if not os.path.isdir(args.dir):
        print(f"Error: Directory does not exist: {args.dir}")
        sys.exit(1)

    agent = VibeAgent(
        api_key=args.key,
        work_dir=args.dir,
        server_url=args.server,
        new_session=args.new_session
    )

    # Reconnection logic
    while True:
        try:
            await agent.connect()
        except KeyboardInterrupt:
            logger.info("Shutting down.")
            break
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            logger.info("Reconnecting in 5 seconds...")
            await asyncio.sleep(5)


def cli_main():
    """CLI entry point"""
    asyncio.run(main())


if __name__ == "__main__":
    cli_main()
