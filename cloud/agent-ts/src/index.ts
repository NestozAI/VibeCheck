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
console.log(`Working directory: ${workDir}`);
console.log(`Server: ${opts.server}`);
console.log(`New session: ${opts.newSession}`);
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
        console.log("\n[agent] Shutting down.");
        process.exit(0);
      }
      console.error(
        `[agent] Connection failed: ${error instanceof Error ? error.message : error}`,
      );
    }
    console.log(
      `[agent] Reconnecting in ${RECONNECT_DELAY_MS / 1000}s...`,
    );
    await new Promise((r) => setTimeout(r, RECONNECT_DELAY_MS));
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
