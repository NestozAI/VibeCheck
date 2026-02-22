#!/usr/bin/env node

import { Command } from "commander";
import path from "node:path";
import { VibeAgent } from "./agent.js";
import { DEFAULT_SERVER, RECONNECT_DELAY_MS } from "./config.js";

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
console.log(`작업 디렉토리: ${workDir}`);
console.log(`서버: ${opts.server}`);
console.log(`새 세션: ${opts.newSession}`);
console.log("");

const agent = new VibeAgent(opts.key, workDir, opts.server, opts.newSession);

async function main(): Promise<void> {
  while (true) {
    try {
      await agent.connect();
    } catch (error) {
      if (
        error instanceof Error &&
        (error.message.includes("SIGINT") ||
          error.message.includes("SIGTERM"))
      ) {
        console.log("\n[agent] 종료합니다.");
        process.exit(0);
      }
      console.error(
        `[agent] 연결 실패: ${error instanceof Error ? error.message : error}`,
      );
    }
    console.log(
      `[agent] ${RECONNECT_DELAY_MS / 1000}초 후 재연결 시도...`,
    );
    await new Promise((r) => setTimeout(r, RECONNECT_DELAY_MS));
  }
}

// Graceful shutdown
process.on("SIGINT", () => {
  console.log("\n[agent] SIGINT 수신. 종료합니다.");
  process.exit(0);
});

process.on("SIGTERM", () => {
  console.log("\n[agent] SIGTERM 수신. 종료합니다.");
  process.exit(0);
});

main().catch((e) => {
  console.error("[agent] 치명적 오류:", e);
  process.exit(1);
});
