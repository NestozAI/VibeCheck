/**
 * Optional Slack integration using @slack/bolt.
 * Only loaded when SLACK_BOT_TOKEN and SLACK_APP_TOKEN are set.
 */

import type { VibeCheckCore } from "../core.js";
import {
  SLACK_BOT_TOKEN,
  SLACK_APP_TOKEN,
  WORK_DIR,
  getMsg,
  getUserLang,
  userLangOverride,
} from "../config.js";
import {
  buildApprovalBlocks,
  buildMessageWithDeleteButton,
  buildTrustedPathsBlocks,
} from "./ui-builder.js";

export function createSlackApp(core: VibeCheckCore) {
  // Dynamic import — fails gracefully if @slack/bolt is not installed
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { App } = require("@slack/bolt") as typeof import("@slack/bolt");

  const app = new App({
    token: SLACK_BOT_TOKEN,
    appToken: SLACK_APP_TOKEN,
    socketMode: true,
  });

  // ------------------------------------------------------------------
  // Helper
  // ------------------------------------------------------------------

  function extractMessageText(event: Record<string, unknown>): string {
    const text = String(event.text ?? "");
    return text.replace(/<@[A-Z0-9]+>/g, "").trim();
  }

  // ------------------------------------------------------------------
  // Core message processing via shared VibeCheckCore
  // ------------------------------------------------------------------

  async function processMessage(
    say: (msg: Record<string, unknown>) => Promise<Record<string, unknown>>,
    threadTs: string,
    userMessage: string,
    client?: any,
    channel?: string,
    userId?: string,
  ) {
    const lang = getUserLang(userId);
    const msgLower = userMessage.toLowerCase().trim();

    // Language setting command (Slack-only)
    if (msgLower.startsWith("/lang")) {
      const parts = msgLower.split(/\s+/);
      if (parts.length === 2 && (parts[1] === "en" || parts[1] === "ko")) {
        if (userId) userLangOverride.set(userId, parts[1]);
        await say({
          text: `Language set to ${parts[1] === "en" ? "English" : "Korean"}`,
          thread_ts: threadTs,
        });
      } else {
        await say({ text: "Usage: `/lang en` or `/lang ko`", thread_ts: threadTs });
      }
      return;
    }

    // Trusted paths list (Slack block kit version)
    if (msgLower === "/paths") {
      const blocks = buildTrustedPathsBlocks(core.security.getTrustedPaths());
      await say({ blocks, text: "Trusted paths list", thread_ts: threadTs });
      return;
    }

    // Delegate to core with Slack-specific callbacks
    let thinkingTs: string | null = null;

    // Wire security approval to Slack (must be set before calling handleQuery)
    core.security.onApprovalNeeded = async (paths, toolName, input) => {
      const blocks = buildApprovalBlocks(
        toolName,
        paths,
        `${toolName}: ${JSON.stringify(input).slice(0, 100)}`,
      );
      await say({ blocks, text: "Security approval required", thread_ts: threadTs });
    };

    // Send thinking message BEFORE starting the query
    const thinkingResult = await say({
      text: getMsg("thinking", lang),
      thread_ts: threadTs,
    });
    thinkingTs = (thinkingResult as Record<string, unknown>)?.ts as string ?? null;

    await core.handleQuery(
      userMessage,
      {
        onResponse: (result, images, _meta) => {
          // Delete thinking message
          if (thinkingTs && client && channel) {
            try {
              client.chat_delete({ channel, ts: thinkingTs });
            } catch {
              // ignore
            }
          }

          const blocks = buildMessageWithDeleteButton(result);
          say({ blocks, text: result, thread_ts: threadTs });

          // Upload images if any
          if (images.length > 0 && client && channel) {
            for (const img of images) {
              try {
                client.files_uploadV2({
                  channel_id: channel,
                  thread_ts: threadTs,
                  file: Buffer.from(img.data, "base64"),
                  filename: img.filename,
                  title: getMsg("image_generated", lang),
                });
              } catch (e) {
                console.error("[slack] Image upload failed:", e);
              }
            }
          }
        },
      },
    );
  }

  // ------------------------------------------------------------------
  // Event handlers
  // ------------------------------------------------------------------

  app.event("app_mention", async ({ event, say, client }: any) => {
    const userMessage = extractMessageText(event);
    const threadTs = event.thread_ts ?? event.ts;
    const channel = event.channel;
    const userId = event.user;

    if (!userMessage) {
      await say({ text: "How can I help you?", thread_ts: threadTs });
      return;
    }

    await processMessage(say, threadTs, userMessage, client, channel, userId);
  });

  app.event("message", async ({ event, say, client }: any) => {
    if (event.bot_id) return;
    if (event.channel_type !== "im") return;

    const userMessage = String(event.text ?? "").trim();
    if (!userMessage) return;

    const threadTs = event.thread_ts ?? event.ts;
    const channel = event.channel;
    const userId = event.user;

    await processMessage(say, threadTs, userMessage, client, channel, userId);
  });

  // ------------------------------------------------------------------
  // Action handlers
  // ------------------------------------------------------------------

  app.action("approve_access", async ({ ack, body, client }: any) => {
    await ack();
    client.chat_update({
      channel: body.channel.id,
      ts: body.message.ts,
      text: `Approved (one-time) by @${body.user.username}`,
      blocks: [{ type: "section", text: { type: "mrkdwn", text: `Approved (one-time) by @${body.user.username}` } }],
    });
    core.security.resolveApproval(true, false);
  });

  app.action("approve_permanent", async ({ ack, body, client }: any) => {
    await ack();
    client.chat_update({
      channel: body.channel.id,
      ts: body.message.ts,
      text: `Approved (permanent) by @${body.user.username}`,
      blocks: [{ type: "section", text: { type: "mrkdwn", text: `Approved (permanent) by @${body.user.username}` } }],
    });
    core.security.resolveApproval(true, true);
  });

  app.action("deny_access", async ({ ack, body, client }: any) => {
    await ack();
    client.chat_update({
      channel: body.channel.id,
      ts: body.message.ts,
      text: `Denied by @${body.user.username}`,
      blocks: [{ type: "section", text: { type: "mrkdwn", text: `Denied by @${body.user.username}` } }],
    });
    core.security.resolveApproval(false, false);
  });

  app.action("remove_trusted_path", async ({ ack, body, client }: any) => {
    await ack();
    const pathToRemove = body.actions[0].value;
    core.security.removeTrustedPath(pathToRemove);
    const blocks = buildTrustedPathsBlocks(core.security.getTrustedPaths());
    client.chat_update({
      channel: body.channel.id,
      ts: body.message.ts,
      text: "Trusted paths list",
      blocks,
    });
  });

  app.action("delete_message", async ({ ack, body, client }: any) => {
    await ack();
    try {
      await client.chat_delete({ channel: body.channel.id, ts: body.message.ts });
    } catch (e) {
      console.error("[slack] Message deletion failed:", e);
    }
  });

  // ------------------------------------------------------------------
  // App Home
  // ------------------------------------------------------------------

  app.event("app_home_opened", async ({ event, client }: any) => {
    const trustedCount = core.security.getTrustedPaths().length;

    await client.views.publish({
      user_id: event.user,
      view: {
        type: "home",
        blocks: [
          { type: "header", text: { type: "plain_text", text: "VibeCheck", emoji: true } },
          { type: "section", text: { type: "mrkdwn", text: "Remotely control the Claude Code CLI from Slack." } },
          { type: "divider" },
          {
            type: "section",
            text: {
              type: "mrkdwn",
              text: `*Working directory:* \`${WORK_DIR}\`\n*Trusted paths:* ${trustedCount}`,
            },
          },
          { type: "divider" },
          {
            type: "section",
            text: {
              type: "mrkdwn",
              text: [
                "*Usage:*",
                "- Send a DM and Claude will respond",
                "- Mention `@bot message` in a channel",
                "",
                "*Commands:*",
                "- `reset` - Start new conversation",
                "- `help` - Show help",
                "- `/paths` - Trusted paths list",
                "- `/trust /path` - Add trusted path",
              ].join("\n"),
            },
          },
        ],
      },
    });
  });

  // ------------------------------------------------------------------
  // Return app for starting
  // ------------------------------------------------------------------

  return {
    async start() {
      await app.start();
      console.log("[slack] Slack handler started (Socket Mode)");
    },
  };
}
