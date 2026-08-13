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

  // Watchdog: "연결이 없는 상태"가 5분 지속되면 프로세스 종료 → systemd 재시작.
  // 주의: agent.connect()의 Promise는 연결이 "닫힐 때" resolve되므로, 연결 성공
  // 시점의 해제는 반드시 onConnected 콜백(open 이벤트)에서 해야 한다 — resolve
  // 이후에 리셋하면 살아 있는 연결 중에도 타이머가 터진다 (5분마다 재시작하며
  // 5분 이상 걸리는 작업을 전부 죽이던 버그의 원인).
  let watchdog: ReturnType<typeof setTimeout> | null = null;
  const disarmWatchdog = () => {
    if (watchdog) clearTimeout(watchdog);
    watchdog = null;
  };
  const armWatchdog = () => {
    disarmWatchdog();
    watchdog = setTimeout(() => {
      console.error(`[agent] Watchdog: no connection for ${WATCHDOG_TIMEOUT_MS / 60000}min. Exiting for clean restart.`);
      process.exit(1);
    }, WATCHDOG_TIMEOUT_MS);
    watchdog.unref(); // don't prevent exit
  };

  // 연결이 열리면 watchdog 해제 + 실패 카운터 리셋
  agent.onConnected = () => {
    disarmWatchdog();
    consecutiveFailures = 0;
  };

  armWatchdog();

  while (true) {
    try {
      await agent.connect(); // resolves when the connection CLOSES
      armWatchdog(); // 연결이 끊긴 시점부터 무연결 카운트 시작
    } catch (error) {
      armWatchdog(); // 연결 실패/오류 — 무연결 상태이므로 다시 감시
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
