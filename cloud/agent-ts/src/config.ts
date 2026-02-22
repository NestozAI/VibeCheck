import path from "node:path";
import os from "node:os";

export const DEFAULT_SERVER = "wss://vibecheck.nestoz.co/ws/agent";
export const SESSION_DIR = path.join(os.homedir(), ".vibecheck");
export const PING_INTERVAL_MS = 15_000;
export const RECONNECT_DELAY_MS = 5_000;
export const COMMAND_TIMEOUT_MS = 300_000; // 5 minutes
export const IMAGE_SCAN_TIMEOUT_MS = 2_000;
export const MAX_IMAGES_PER_RESPONSE = 5;
export const SESSION_SYNC_TIMEOUT_MS = 5_000;

export const IMAGE_EXTENSIONS = new Set([
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".webp",
  ".bmp",
]);

export const SKIP_DIRS = new Set([
  "node_modules",
  ".git",
  "__pycache__",
  "venv",
  ".venv",
  "dist",
  "build",
  ".next",
]);

export const SAFE_SYSTEM_COMMANDS = new Set([
  "nvidia-smi",
  "df",
  "free",
  "uptime",
  "whoami",
  "hostname",
  "cat /proc/cpuinfo",
  "cat /proc/meminfo",
  "ps",
  "top -bn1",
  "ls",
  "pwd",
  "date",
  "which",
  "echo",
  "git status",
  "git log",
  "git diff",
]);

export const SCREENSHOT_KEYWORDS = [
  "스크린샷",
  "screenshot",
  "캡처",
  "capture",
  "보여줘",
  "show me",
  "preview",
  "미리보기",
  "ui",
];
