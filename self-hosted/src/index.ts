import { VibeCheckCore } from "./core.js";
import { createWebServer } from "./server.js";
import { WORK_DIR, WEB_PORT, WEB_HOST, SLACK_ENABLED } from "./config.js";

async function main() {
  console.log("=== VibeCheck Self-Hosted ===");
  console.log(`Working directory: ${WORK_DIR}`);
  console.log(`Web UI: http://${WEB_HOST === "0.0.0.0" ? "localhost" : WEB_HOST}:${WEB_PORT}`);
  console.log(`Slack: ${SLACK_ENABLED ? "enabled" : "disabled"}`);
  console.log("");

  const core = new VibeCheckCore(WORK_DIR);
  const webServer = createWebServer(core);

  // Optional Slack integration
  if (SLACK_ENABLED) {
    try {
      const { createSlackApp } = await import("./slack/handler.js");
      const slackApp = createSlackApp(core);
      await slackApp.start();
      console.log("[slack] Slack handler started");
    } catch (e) {
      console.error("[slack] Failed to start:", e instanceof Error ? e.message : e);
      console.log("[slack] Continuing without Slack integration");
    }
  }

  webServer.start();
}

// Graceful shutdown
process.on("SIGINT", () => {
  console.log("\nShutting down.");
  process.exit(0);
});
process.on("SIGTERM", () => {
  console.log("\nShutting down.");
  process.exit(0);
});

main().catch((e) => {
  console.error("Fatal error:", e);
  process.exit(1);
});
