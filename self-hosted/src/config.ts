import dotenv from "dotenv";
import path from "node:path";
import os from "node:os";

dotenv.config();

// =============================================================================
// Environment variables
// =============================================================================

export const WORK_DIR = process.env.WORK_DIR
  ? path.resolve(process.env.WORK_DIR)
  : process.cwd();

export const WEB_PORT = parseInt(process.env.WEB_PORT || "8501", 10);
export const WEB_HOST = process.env.WEB_HOST || "0.0.0.0";

export const SLACK_BOT_TOKEN = process.env.SLACK_BOT_TOKEN || "";
export const SLACK_APP_TOKEN = process.env.SLACK_APP_TOKEN || "";
export const SLACK_ENABLED = !!(SLACK_BOT_TOKEN && SLACK_APP_TOKEN);

export const BOT_LANG = process.env.BOT_LANG || "en";

// =============================================================================
// Constants (consumed by shared modules via shared/config.ts bridge)
// =============================================================================

export const SESSION_DIR = path.join(os.homedir(), ".vibecheck");

export const IMAGE_EXTENSIONS = new Set([
  ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
]);

export const SKIP_DIRS = new Set([
  "node_modules", ".git", "__pycache__", "venv", ".venv",
  "dist", "build", ".next",
]);

export const SAFE_SYSTEM_COMMANDS = new Set([
  "nvidia-smi", "df", "free", "uptime", "whoami", "hostname",
  "cat /proc/cpuinfo", "cat /proc/meminfo", "ps", "top -bn1",
  "ls", "pwd", "date", "which", "echo",
  "git status", "git log", "git diff",
]);

export const SCREENSHOT_KEYWORDS = [
  "screenshot", "capture", "show me", "show", "preview", "ui",
];

export const IMAGE_SCAN_TIMEOUT_MS = 2_000;
export const MAX_IMAGES_PER_RESPONSE = 5;
export const COMMAND_TIMEOUT_MS = 300_000;

// =============================================================================
// Multilingual messages
// =============================================================================

export const MESSAGES: Record<string, Record<string, string>> = {
  ko: {
    thinking: "Claude is thinking...",
    approved_running: "Approved! Claude is running...",
    no_response: "Claude did not respond.",
    image_generated: "Generated image",
    image_referenced: "Referenced image",
    image_related: "Related image",
    security_warning: "*Security Warning*\n\nAI is trying to access the following paths:",
    request_label: "Request:",
    btn_approve_run: "Approve & Run",
    btn_approve_permanent: "Approve (Permanent)",
    btn_deny: "Deny",
    paths_title: "*Trusted Paths*",
    paths_empty: "No trusted paths registered.",
    path_added: "Trusted path added:",
    path_already: "Already a trusted path:",
    path_invalid: "Invalid path:",
    trust_usage: "Usage: `/trust /path/name`",
    help_title: "*VibeCheck Help*",
  },
  en: {
    thinking: "Claude is thinking...",
    approved_running: "Approved! Claude is running...",
    no_response: "Claude did not respond.",
    image_generated: "Generated image",
    image_referenced: "Referenced image",
    image_related: "Related image",
    security_warning: "*Security Warning*\n\nAI is trying to access the following paths:",
    request_label: "Request:",
    btn_approve_run: "Approve & Run",
    btn_approve_permanent: "Approve (Permanent)",
    btn_deny: "Deny",
    paths_title: "*Trusted Paths*",
    paths_empty: "No trusted paths registered.",
    path_added: "Trusted path added:",
    path_already: "Already a trusted path:",
    path_invalid: "Invalid path:",
    trust_usage: "Usage: `/trust /path/name`",
    help_title: "*VibeCheck Help*",
  },
};

export function getMsg(key: string, lang?: string): string {
  const useLang = lang || BOT_LANG || "en";
  return MESSAGES[useLang]?.[key] ?? MESSAGES.en[key] ?? key;
}

// Per-user language overrides
export const userLangOverride: Map<string, string> = new Map();

export function getUserLang(userId?: string): string {
  if (userId && userLangOverride.has(userId)) {
    return userLangOverride.get(userId)!;
  }
  return BOT_LANG;
}
