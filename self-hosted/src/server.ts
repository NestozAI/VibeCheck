import express from "express";
import { createServer } from "node:http";
import { WebSocketServer, WebSocket } from "ws";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { VibeCheckCore } from "./core.js";
import { getAllSkills } from "./shared/skills.js";
import type { ClientMessage, ServerMessage } from "./protocol.js";
import { WEB_PORT, WEB_HOST, WORK_DIR } from "./config.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export function createWebServer(core: VibeCheckCore) {
  const app = express();
  const server = createServer(app);
  const wss = new WebSocketServer({ server, path: "/ws" });

  // Track connected clients for broadcast
  const clients = new Set<WebSocket>();

  // Serve static files
  const staticDir = path.join(__dirname, "..", "static");
  app.use("/static", express.static(staticDir));
  app.get("/", (_req, res) => {
    res.sendFile(path.join(staticDir, "index.html"));
  });

  // Broadcast to all connected clients
  function broadcast(msg: ServerMessage) {
    const data = JSON.stringify(msg);
    for (const ws of clients) {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(data);
      }
    }
  }

  core.setBroadcast(broadcast);

  wss.on("connection", (ws: WebSocket) => {
    console.log("[server] Client connected");
    clients.add(ws);

    // Wire security approval to this client
    core.security.onApprovalNeeded = (
      paths: string[],
      toolName: string,
      input: Record<string, unknown>,
    ) => {
      sendTo(ws, {
        type: "approval_required",
        paths,
        message: `${toolName}: ${JSON.stringify(input).slice(0, 200)}`,
      });
    };

    ws.on("message", async (data) => {
      try {
        const msg: ClientMessage = JSON.parse(data.toString());
        await handleClientMessage(ws, core, msg);
      } catch (e) {
        console.error("[server] Message error:", e);
        sendTo(ws, { type: "error", message: "Invalid message format" });
      }
    });

    ws.on("close", () => {
      console.log("[server] Client disconnected");
      clients.delete(ws);
    });

    ws.on("error", (err) => {
      console.error("[server] WebSocket error:", err.message);
      clients.delete(ws);
    });
  });

  return {
    start() {
      server.listen(WEB_PORT, WEB_HOST, () => {
        console.log(`[server] Web UI: http://${WEB_HOST}:${WEB_PORT}`);
      });
    },
  };
}

async function handleClientMessage(
  ws: WebSocket,
  core: VibeCheckCore,
  msg: ClientMessage,
) {
  switch (msg.type) {
    case "query":
      await core.handleQuery(
        msg.message,
        {
          onStreamingChunk: (delta, index) =>
            sendTo(ws, { type: "streaming_chunk", delta, index }),
          onToolStatus: (tool, status, label, detail) =>
            sendTo(ws, {
              type: "tool_status",
              tool,
              status,
              label,
              ...(detail ? { detail } : {}),
            }),
          onResponse: (result, images, meta) =>
            sendTo(ws, {
              type: "response",
              result,
              ...(images.length > 0 ? { images } : {}),
              ...(meta.cost_usd !== undefined ? { cost_usd: meta.cost_usd } : {}),
              ...(meta.num_turns !== undefined ? { num_turns: meta.num_turns } : {}),
              ...(meta.usage ? { usage: meta.usage } : {}),
            }),
        },
        msg.model,
        msg.skill_id,
        msg.system_prompt,
      );
      break;

    case "approval":
      core.security.resolveApproval(msg.approved, msg.permanent ?? false);
      break;

    case "interrupt": {
      const interrupted = await core.interrupt();
      if (interrupted) {
        sendTo(ws, { type: "response", result: "Task interrupted." });
      }
      break;
    }

    case "ping":
      sendTo(ws, { type: "pong" });
      break;

    case "skill_list":
      sendTo(ws, {
        type: "skill_list_response",
        skills: getAllSkills().map((s) => ({
          id: s.id,
          name: s.name,
          icon: s.icon,
          description: s.description,
        })),
      });
      break;

    case "schedule_list":
      sendTo(ws, {
        type: "schedule_list_response",
        tasks: core.scheduler.getAll(),
      });
      break;

    case "schedule_add": {
      const result = core.scheduler.addTask(msg.cron, msg.message, msg.skill_id);
      if ("error" in result) {
        sendTo(ws, { type: "schedule_add_response", success: false, error: result.error });
      } else {
        sendTo(ws, { type: "schedule_add_response", success: true, task: result });
      }
      break;
    }

    case "schedule_remove":
      core.scheduler.removeTask(msg.id);
      break;

    case "schedule_toggle":
      core.scheduler.toggleTask(msg.id, msg.enabled);
      break;
  }
}

function sendTo(ws: WebSocket, msg: ServerMessage) {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(msg));
  }
}
