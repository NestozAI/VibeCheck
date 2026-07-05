#!/usr/bin/env node

import { Command } from "commander";
import path from "node:path";
import { VibeAgent } from "./agent.js";
import { DEFAULT_SERVER, RECONNECT_DELAY_MS, MAX_RECONNECT_DELAY_MS, MAX_CONSECUTIVE_FAILURES, WATCHDOG_TIMEOUT_MS } from "./config.js";
import { checkForUpdates } from "./updater.js";

const program = new Command()
  .name("vibecheck-agent")
  .description("VibeCheck Agent - Remote control Claude Code from anywhere")
  .requiredOption("--key <key>", "API Key (vibe_sk_...)")
  .option("--dir <dir>", "Working directory", process.cwd())
  .option("--server <url>", "Server URL", DEFAULT_SERVER)
  .option("--new-session", "Start a new session", false)
  .version("1.0.0")
  .parse();

const opts = program.opts<{
  key: string;
  dir: string;
  server: string;
  newSession: boolean;
}>();

const workDir = path.resolve(opts.dir);

console.log("=== VibeCheck Agent (TypeScript + Claude Agent SDK) ===");
console.log(`Working directory: ${workDir}`);
console.log(`Server: ${opts.server}`);
console.log(`New session: ${opts.newSession}`);
console.log("");

const agent = new VibeAgent(opts.key, workDir, opts.server, opts.newSession);

async function main(): Promise<void> {
  // Auto-update on startup
  const updated = await checkForUpdates();
  if (updated) {
    // Re-exec with the updated binary
    const { spawn } = await import("node:child_process");
    const child = spawn(process.argv[0], process.argv.slice(1), {
      stdio: "inherit",
      env: process.env,
    });
    child.on("exit", (code) => process.exit(code ?? 0));
    return;
  }

  let consecutiveFailures = 0;

  // Watchdog: 5분간 서버 연결 성공이 없으면 프로세스 종료 → systemd 재시작
  let watchdog: ReturnType<typeof setTimeout> | null = null;
  const resetWatchdog = () => {
    if (watchdog) clearTimeout(watchdog);
    watchdog = setTimeout(() => {
      console.error(`[agent] Watchdog: no connection for ${WATCHDOG_TIMEOUT_MS / 60000}min. Exiting for clean restart.`);
      process.exit(1);
    }, WATCHDOG_TIMEOUT_MS);
    watchdog.unref(); // don't prevent exit
  };
  resetWatchdog();

  while (true) {
    try {
      await agent.connect();
      consecutiveFailures = 0; // Reset on successful connection
      resetWatchdog(); // 연결 성공 시 watchdog 리셋
    } catch (error) {
      if (
        error instanceof Error &&
        (error.message.includes("SIGINT") ||
          error.message.includes("SIGTERM"))
      ) {
        console.log("\n[agent] Shutting down.");
        process.exit(0);
      }
      consecutiveFailures++;
      console.error(
        `[agent] Connection failed (${consecutiveFailures}/${MAX_CONSECUTIVE_FAILURES}): ${error instanceof Error ? error.message : error}`,
      );

      // Too many consecutive failures — exit and let systemd restart us
      if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) {
        console.error(`[agent] ${MAX_CONSECUTIVE_FAILURES} consecutive failures. Exiting for clean restart.`);
        process.exit(1);
      }
    }
    // Check for updates on each reconnect
    const reconnectUpdated = await checkForUpdates();
    if (reconnectUpdated) {
      console.log("[agent] Re-launching with updated version...");
      const { spawn } = await import("node:child_process");
      const child = spawn(process.argv[0], process.argv.slice(1), {
        stdio: "inherit",
        env: process.env,
      });
      child.on("exit", (code) => process.exit(code ?? 0));
      return;
    }
    // Exponential backoff: 5s → 10s → 20s → 40s → 60s (cap)
    const delay = Math.min(RECONNECT_DELAY_MS * Math.pow(2, consecutiveFailures - 1), MAX_RECONNECT_DELAY_MS);
    console.log(
      `[agent] Reconnecting in ${(delay / 1000).toFixed(0)}s...`,
    );
    await new Promise((r) => setTimeout(r, delay));
  }
}

// Graceful shutdown
process.on("SIGINT", () => {
  console.log("\n[agent] SIGINT received. Shutting down.");
  process.exit(0);
});

process.on("SIGTERM", () => {
  console.log("\n[agent] SIGTERM received. Shutting down.");
  process.exit(0);
});

// Prevent silent crashes from unhandled promise rejections
process.on("unhandledRejection", (reason) => {
  console.error("[agent] Unhandled rejection:", reason);
});

process.on("uncaughtException", (error) => {
  console.error("[agent] Uncaught exception:", error);
  // Don't exit — let the reconnect loop handle it
});

main().catch((e) => {
  console.error("[agent] Fatal error:", e);
  process.exit(1);
});
