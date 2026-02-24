import path from "node:path";
import {
  ClaudeSession,
  AbortError,
  type ExecuteResult,
} from "./shared/claude.js";
import { SecurityManager } from "./shared/security.js";
import {
  getImagesWithMtime,
  findNewOrModifiedImages,
  imageToBase64,
  extractImagePathsFromText,
} from "./shared/images.js";
import {
  screenshotProject,
  findProjectDir,
  getScreenshotPath,
} from "./shared/screenshot.js";
import { saveSessionId, loadSessionId, clearSessionId } from "./shared/session.js";
import { getSkill, getAllSkills } from "./shared/skills.js";
import { TaskScheduler, type ScheduledTask } from "./shared/scheduler.js";
import { cleanOutput } from "./cleaner.js";
import {
  WORK_DIR,
  SCREENSHOT_KEYWORDS,
  IMAGE_SCAN_TIMEOUT_MS,
  MAX_IMAGES_PER_RESPONSE,
  getMsg,
} from "./config.js";
import type { ImageData, ServerMessage } from "./protocol.js";

// Utility: timeout wrapper
async function withTimeout<T>(
  fn: () => Promise<T>,
  ms: number,
  fallback: T,
): Promise<T> {
  try {
    return await Promise.race([
      fn(),
      new Promise<T>((_, reject) =>
        setTimeout(() => reject(new Error("timeout")), ms),
      ),
    ]);
  } catch {
    return fallback;
  }
}

// Tool label mapping
const TOOL_LABELS: Record<string, Record<string, string>> = {
  Read: { start: "Reading file", end: "File read complete" },
  Write: { start: "Writing file", end: "File written" },
  Edit: { start: "Editing file", end: "File edited" },
  Bash: { start: "Running command", end: "Command finished" },
  Glob: { start: "Searching files", end: "Search complete" },
  Grep: { start: "Searching content", end: "Search complete" },
  WebFetch: { start: "Fetching URL", end: "Fetch complete" },
  WebSearch: { start: "Searching web", end: "Search complete" },
  Task: { start: "Running sub-agent", end: "Sub-agent complete" },
};

function getToolLabel(tool: string, status: "start" | "end"): string {
  return TOOL_LABELS[tool]?.[status] ?? `${tool} ${status === "start" ? "started" : "finished"}`;
}

// Callbacks interface for query results
export interface QueryCallbacks {
  onStreamingChunk?: (delta: string, index: number) => void;
  onToolStatus?: (
    tool: string,
    status: "start" | "end",
    label: string,
    detail?: string,
  ) => void;
  onResponse: (
    result: string,
    images: ImageData[],
    metadata: {
      cost_usd?: number;
      num_turns?: number;
      usage?: ExecuteResult["usage"];
    },
  ) => void;
}

// Broadcast callback for scheduled task results
export type BroadcastFn = (msg: ServerMessage) => void;

export class VibeCheckCore {
  private claude: ClaudeSession;
  readonly security: SecurityManager;
  readonly scheduler: TaskScheduler;
  private processing = false;
  private pendingScheduledTasks: ScheduledTask[] = [];
  private broadcast: BroadcastFn | null = null;

  constructor(workDir: string, newSession = false) {
    this.security = new SecurityManager(workDir);
    this.scheduler = new TaskScheduler();

    let sessionId: string | null = null;
    if (newSession) {
      clearSessionId(workDir);
    } else {
      sessionId = loadSessionId(workDir);
    }

    this.claude = new ClaudeSession({
      workDir,
      sessionId,
      security: this.security,
    });

    // Persist session ID when SDK provides one
    this.claude.onSessionId = (id: string) => {
      saveSessionId(workDir, id);
    };

    // Wire scheduler
    this.scheduler.onTaskFire = async (task: ScheduledTask) => {
      if (this.processing) {
        this.pendingScheduledTasks.push(task);
        return;
      }
      await this.runScheduledTask(task);
    };
    this.scheduler.start();
  }

  setBroadcast(fn: BroadcastFn) {
    this.broadcast = fn;
  }

  get isProcessing(): boolean {
    return this.processing;
  }

  async handleQuery(
    message: string,
    callbacks: QueryCallbacks,
    model?: string,
    skillId?: string,
    systemPrompt?: string,
  ): Promise<void> {
    // Handle built-in commands
    const cmd = this.handleCommand(message);
    if (cmd !== null) {
      callbacks.onResponse(cmd, [], {});
      return;
    }

    if (this.processing) {
      callbacks.onResponse("A previous task is still running. Please wait.", [], {});
      return;
    }

    this.processing = true;
    console.log(`[core] Query: ${message.slice(0, 80)}...`);

    // Wire streaming callbacks
    this.claude.onStreamingChunk = callbacks.onStreamingChunk;
    this.claude.onToolStatus = (tool, status, detail) => {
      callbacks.onToolStatus?.(tool, status, getToolLabel(tool, status), detail);
    };

    try {
      // Snapshot images before execution
      const beforeImages = await withTimeout(
        () => Promise.resolve(getImagesWithMtime(WORK_DIR)),
        IMAGE_SCAN_TIMEOUT_MS,
        {},
      );

      // Execute with optional skill
      const skill = skillId ? getSkill(skillId) : undefined;
      if (skill) console.log(`[core] Skill: ${skill.icon} ${skill.name}`);

      const execResult = await this.claude.execute(
        message,
        model,
        skill,
        systemPrompt,
      );

      // Clean output
      const cleaned = cleanOutput(execResult.text) ?? execResult.text;

      // Collect images
      const images: ImageData[] = [];

      // Screenshot (keyword detection)
      const wantsScreenshot = SCREENSHOT_KEYWORDS.some((kw) =>
        message.toLowerCase().includes(kw),
      );
      if (wantsScreenshot) {
        const screenshot = await this.generateScreenshot(message, execResult.text);
        if (screenshot) images.push(screenshot);
      }

      // New/modified images
      const newImages = findNewOrModifiedImages(WORK_DIR, beforeImages);
      for (const imgPath of newImages.slice(0, MAX_IMAGES_PER_RESPONSE - images.length)) {
        const b64 = imageToBase64(imgPath);
        if (b64) {
          images.push({ filename: path.basename(imgPath), data: b64 });
        }
      }

      // Referenced images in response text
      if (images.length === 0) {
        const referenced = extractImagePathsFromText(execResult.text, WORK_DIR);
        for (const imgPath of referenced.slice(0, MAX_IMAGES_PER_RESPONSE)) {
          const b64 = imageToBase64(imgPath);
          if (b64) {
            images.push({ filename: path.basename(imgPath), data: b64 });
          }
        }
      }

      console.log(
        `[core] Response: ${cleaned.length} chars, ${images.length} images` +
          (execResult.cost_usd !== undefined ? `, $${execResult.cost_usd.toFixed(4)}` : ""),
      );

      callbacks.onResponse(cleaned, images, {
        cost_usd: execResult.cost_usd,
        num_turns: execResult.num_turns,
        usage: execResult.usage,
      });
    } catch (e) {
      if (e instanceof AbortError) return;
      const errMsg = e instanceof Error ? e.message : String(e);
      console.error("[core] Query error:", errMsg);
      callbacks.onResponse(`Error: ${errMsg}`, [], {});
    } finally {
      this.processing = false;
      this.claude.onStreamingChunk = undefined;
      this.claude.onToolStatus = undefined;
      void this.drainScheduledQueue();
    }
  }

  async interrupt(): Promise<boolean> {
    if (!this.processing) return false;
    return this.claude.interrupt();
  }

  resetSession() {
    clearSessionId(WORK_DIR);
    // Force new session on next execute
    (this.claude as any).currentSessionIdOverride = undefined;
    (this.claude as any).sessionStarted = false;
  }

  // Built-in commands
  private handleCommand(message: string): string | null {
    const trimmed = message.trim().toLowerCase();

    if (trimmed === "/reset") {
      this.resetSession();
      return "Session reset. Starting fresh conversation.";
    }

    if (trimmed === "/help") {
      return [
        "**VibeCheck Commands**",
        "",
        "`/reset` — Reset conversation (start fresh)",
        "`/help` — Show this help",
        "`/paths` — List trusted paths",
        "`/trust /path/to/dir` — Add trusted path",
        "",
        `Working directory: \`${WORK_DIR}\``,
      ].join("\n");
    }

    if (trimmed === "/paths") {
      const paths = this.security.getTrustedPaths();
      if (paths.length === 0) return getMsg("paths_empty");
      return `**${getMsg("paths_title")}**\n\n${paths.map((p) => `- \`${p}\``).join("\n")}`;
    }

    if (trimmed.startsWith("/trust ")) {
      const targetPath = message.trim().slice(7).trim();
      if (!targetPath) return getMsg("trust_usage");

      const resolved = path.resolve(targetPath);
      if (this.security.isPathTrusted(resolved)) {
        return `${getMsg("path_already")} \`${resolved}\``;
      }
      this.security.addTrustedPath(resolved);
      return `${getMsg("path_added")} \`${resolved}\``;
    }

    return null;
  }

  private async generateScreenshot(
    message: string,
    result: string,
  ): Promise<ImageData | null> {
    try {
      const projectDir = findProjectDir(message + "\n" + result, WORK_DIR);
      if (!projectDir) return null;

      const outputPath = getScreenshotPath();
      const screenshotPath = await screenshotProject(projectDir, outputPath);
      if (!screenshotPath) return null;

      const b64 = imageToBase64(screenshotPath);
      if (!b64) return null;

      return { filename: "screenshot.png", data: b64 };
    } catch (e) {
      console.error("[core] Screenshot failed:", e);
      return null;
    }
  }

  private async runScheduledTask(task: ScheduledTask): Promise<void> {
    this.processing = true;
    try {
      const skill = task.skill_id ? getSkill(task.skill_id) : undefined;
      const execResult = await this.claude.execute(task.message, undefined, skill);
      this.scheduler.recordResult(task.id, execResult.text);

      this.broadcast?.({
        type: "response",
        result: `⏰ [${task.cron}] ${execResult.text}`,
        ...(execResult.cost_usd !== undefined ? { cost_usd: execResult.cost_usd } : {}),
        ...(execResult.num_turns !== undefined ? { num_turns: execResult.num_turns } : {}),
      });
    } catch (e) {
      if (!(e instanceof AbortError)) {
        console.error("[scheduler] Task error:", e);
      }
    } finally {
      this.processing = false;
      void this.drainScheduledQueue();
    }
  }

  private async drainScheduledQueue(): Promise<void> {
    const next = this.pendingScheduledTasks.shift();
    if (next) {
      console.log(`[scheduler] Draining: "${next.message.slice(0, 40)}"`);
      await this.runScheduledTask(next);
    }
  }
}
