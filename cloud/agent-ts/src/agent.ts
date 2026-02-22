import WebSocket from "ws";
import path from "node:path";
import type { SDKSystemMessage } from "@anthropic-ai/claude-agent-sdk";
import { ClaudeSession, AbortError } from "./claude.js";
import type { ExecuteResult } from "./claude.js";
import { SecurityManager } from "./security.js";
import {
  getImagesWithMtime,
  findNewOrModifiedImages,
  imageToBase64,
  extractImagePathsFromText,
} from "./images.js";
import {
  screenshotProject,
  findProjectDir,
  getScreenshotPath,
} from "./screenshot.js";
import {
  saveSessionId,
  loadSessionId,
  clearSessionId,
} from "./session.js";
import {
  DEFAULT_SERVER,
  PING_INTERVAL_MS,
  RECONNECT_DELAY_MS,
  IMAGE_SCAN_TIMEOUT_MS,
  MAX_IMAGES_PER_RESPONSE,
  SESSION_SYNC_TIMEOUT_MS,
  SCREENSHOT_KEYWORDS,
} from "./config.js";
import type {
  AgentToServerMessage,
  ServerToAgentMessage,
  ImageData,
  ToolStatusMessage,
  SkillListResponseMessage,
  ScheduleListResponseMessage,
  ScheduleAddResponseMessage,
} from "./protocol.js";
import { getSkill, getAllSkills } from "./skills.js";
import { TaskScheduler, type ScheduledTask } from "./scheduler.js";

export class VibeAgent {
  private ws: WebSocket | null = null;
  private claude: ClaudeSession;
  private security: SecurityManager;
  private scheduler: TaskScheduler;
  private processing = false;
  /** Scheduled tasks that arrived while a user query was in progress */
  private pendingScheduledTasks: ScheduledTask[] = [];
  private pingInterval: ReturnType<typeof setInterval> | null = null;
  private lastProjectPath: string | null = null;

  constructor(
    private apiKey: string,
    private workDir: string,
    private serverUrl: string = DEFAULT_SERVER,
    newSession = false,
  ) {
    this.security = new SecurityManager(workDir);

    // Wire security approval → WebSocket
    this.security.onApprovalNeeded = (paths, toolName, input) => {
      this.send({
        type: "approval_required",
        paths,
        message: `${toolName}: ${JSON.stringify(input).slice(0, 200)}`,
      });
    };

    // Scheduler — fires tasks automatically and sends results via WebSocket
    this.scheduler = new TaskScheduler();
    this.scheduler.onTaskFire = async (task) => {
      if (this.processing) {
        // User query in progress: queue and run after it finishes
        console.log(`[scheduler] 사용자 쿼리 진행 중, 태스크 큐에 추가: "${task.message.slice(0, 40)}"`);
        this.pendingScheduledTasks.push(task);
        return;
      }
      await this.runScheduledTask(task);
    };
    this.scheduler.start();

    // Session management
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

    // When SDK provides new session ID
    this.claude.onSessionId = (id) => {
      saveSessionId(workDir, id);
      this.send({
        type: "session_update",
        work_dir: workDir,
        session_id: id,
      });
    };

    // Forward streaming text chunks to web UI
    this.claude.onStreamingChunk = (delta, index) => {
      this.send({ type: "streaming_chunk", delta, index });
    };

    // Forward tool usage events to web UI as tool_status messages
    this.claude.onToolStatus = (tool, status, detail) => {
      const label = toolLabel(tool, status);
      const toolMsg: ToolStatusMessage = {
        type: "tool_status",
        tool,
        status,
        label,
        ...(detail ? { detail } : {}),
      };
      this.send(toolMsg);
    };

    // Log system init info
    this.claude.onSystemInit = (msg: SDKSystemMessage) => {
      console.log(`[agent] Claude Code 초기화 완료`);
      console.log(`  모델: ${msg.model}`);
      console.log(`  인증: ${msg.apiKeySource}`);
      console.log(`  권한: ${msg.permissionMode}`);
      console.log(`  도구: ${msg.tools.length}개`);
    };
  }

  /**
   * Connect to WebSocket server and start message loop.
   */
  async connect(): Promise<void> {
    const url = `${this.serverUrl}?key=${this.apiKey}`;

    return new Promise<void>((resolve, reject) => {
      this.ws = new WebSocket(url, {
        perMessageDeflate: false,
      });

      this.ws.on("open", async () => {
        console.log("[agent] 서버 연결됨");

        // Start ping loop
        this.startPingLoop();

        // Sync session with server
        await this.syncSession();

        console.log("[agent] 메시지 대기 중...");
      });

      this.ws.on("message", async (data) => {
        try {
          const msg: ServerToAgentMessage = JSON.parse(data.toString());
          await this.handleMessage(msg);
        } catch (e) {
          console.error("[agent] 메시지 처리 오류:", e);
        }
      });

      this.ws.on("close", (code, reason) => {
        console.log(
          `[agent] 연결 종료: ${code} ${reason.toString()}`,
        );
        this.stopPingLoop();
        resolve();
      });

      this.ws.on("error", (error) => {
        console.error("[agent] WebSocket 오류:", error.message);
        this.stopPingLoop();
        reject(error);
      });
    });
  }

  private async handleMessage(msg: ServerToAgentMessage): Promise<void> {
    switch (msg.type) {
      case "query":
        await this.handleQuery(
          msg.message,
          msg.model,
          msg.skill_id,
          msg.system_prompt,
          msg.agents,
        );
        break;

      case "approval":
        this.security.resolveApproval(
          msg.approved,
          msg.permanent ?? false,
        );
        break;

      case "add_trusted_path":
        this.security.addTrustedPath(msg.path);
        break;

      case "interrupt":
        await this.handleInterrupt();
        break;

      case "ping":
        this.send({ type: "pong" });
        break;

      case "pong":
        break;

      case "session_info":
        this.handleSessionInfo(msg);
        break;

      case "error":
        console.error(`[agent] 서버 오류: ${msg.message}`);
        break;

      // ── Skill messages ────────────────────────────────────────────────────
      case "skill_list": {
        const skillList: SkillListResponseMessage = {
          type: "skill_list_response",
          skills: getAllSkills().map((s) => ({
            id: s.id,
            name: s.name,
            icon: s.icon,
            description: s.description,
          })),
        };
        this.send(skillList);
        break;
      }

      // ── Schedule messages ─────────────────────────────────────────────────
      case "schedule_list": {
        const scheduleList: ScheduleListResponseMessage = {
          type: "schedule_list_response",
          tasks: this.scheduler.getAll(),
        };
        this.send(scheduleList);
        break;
      }

      case "schedule_add": {
        const result = this.scheduler.addTask(
          msg.cron,
          msg.message,
          msg.skill_id,
        );
        const addResp: ScheduleAddResponseMessage =
          "error" in result
            ? { type: "schedule_add_response", success: false, error: result.error }
            : { type: "schedule_add_response", success: true, task: result };
        this.send(addResp);
        break;
      }

      case "schedule_remove":
        this.scheduler.removeTask(msg.id);
        break;

      case "schedule_toggle":
        this.scheduler.toggleTask(msg.id, msg.enabled);
        break;
    }
  }

  private async handleQuery(
    message: string,
    model?: string,
    skillId?: string,
    systemPrompt?: string,
    agents?: Record<string, import("./protocol.js").AgentDef>,
  ): Promise<void> {
    if (this.processing) {
      this.send({
        type: "response",
        result: "이전 작업이 아직 실행 중입니다. 잠시 기다려주세요.",
      });
      return;
    }

    this.processing = true;
    console.log(`[agent] 쿼리 수신: ${message.slice(0, 80)}...`);

    try {
      // Before-images snapshot
      const beforeImages = await withTimeout(
        () => getImagesWithMtime(this.workDir),
        IMAGE_SCAN_TIMEOUT_MS,
        {},
      );

      // Execute Claude query (with optional skill preset)
      const skill = skillId ? getSkill(skillId) : undefined;
      if (skill) console.log(`[agent] 스킬 적용: ${skill.icon} ${skill.name}`);
      const execResult: ExecuteResult = await this.claude.execute(
        message,
        model,
        skill,
        systemPrompt,
        agents,
      );

      // Collect images
      const images: ImageData[] = [];

      // Screenshot generation (keyword detection)
      const wantsScreenshot = SCREENSHOT_KEYWORDS.some((kw) =>
        message.toLowerCase().includes(kw),
      );
      if (wantsScreenshot) {
        const screenshot = await this.generateScreenshot(message, execResult.text);
        if (screenshot) images.push(screenshot);
      }

      // Detect new/modified images
      const newImages = findNewOrModifiedImages(this.workDir, beforeImages);
      for (const imgPath of newImages.slice(
        0,
        MAX_IMAGES_PER_RESPONSE - images.length,
      )) {
        const b64 = imageToBase64(imgPath);
        if (b64) {
          images.push({
            filename: path.basename(imgPath),
            data: b64,
          });
        }
      }

      // Extract image paths from response text
      if (images.length === 0) {
        const referenced = extractImagePathsFromText(execResult.text, this.workDir);
        for (const imgPath of referenced.slice(0, MAX_IMAGES_PER_RESPONSE)) {
          const b64 = imageToBase64(imgPath);
          if (b64) {
            images.push({
              filename: path.basename(imgPath),
              data: b64,
            });
          }
        }
      }

      // Send response (with cost + turns + usage metadata)
      const response: AgentToServerMessage = {
        type: "response",
        result: execResult.text,
        ...(images.length > 0 ? { images } : {}),
        ...(execResult.cost_usd !== undefined ? { cost_usd: execResult.cost_usd } : {}),
        ...(execResult.num_turns !== undefined ? { num_turns: execResult.num_turns } : {}),
        ...(execResult.usage ? { usage: execResult.usage } : {}),
      };
      this.send(response);

      if (execResult.cost_usd !== undefined) {
        console.log(
          `[agent] 응답 전송 (${execResult.text.length}자, ${images.length}개 이미지, $${execResult.cost_usd.toFixed(4)}, ${execResult.num_turns}턴)`,
        );
      } else {
        console.log(
          `[agent] 응답 전송 (${execResult.text.length}자, ${images.length}개 이미지)`,
        );
      }
    } catch (e) {
      // interrupt로 인한 AbortError는 handleInterrupt가 응답 메시지를 전송
      // → 여기서는 아무것도 하지 않고 조용히 종료
      if (e instanceof AbortError) return;

      const errMsg = e instanceof Error ? e.message : String(e);
      console.error("[agent] 쿼리 실행 오류:", errMsg);
      this.send({
        type: "response",
        result: `오류: ${errMsg}`,
      });
    } finally {
      this.processing = false;
      // Drain queued scheduled tasks (one at a time)
      void this.drainScheduledQueue();
    }
  }

  /** Run a scheduled task, respecting the processing guard */
  private async runScheduledTask(task: ScheduledTask): Promise<void> {
    if (this.processing) {
      this.pendingScheduledTasks.push(task);
      return;
    }
    this.processing = true;
    try {
      const skill = task.skill_id ? getSkill(task.skill_id) : undefined;
      const execResult = await this.claude.execute(task.message, undefined, skill);
      this.scheduler.recordResult(task.id, execResult.text);
      this.send({
        type: "response",
        result: `⏰ [${task.cron}] ${execResult.text}`,
        ...(execResult.cost_usd !== undefined ? { cost_usd: execResult.cost_usd } : {}),
        ...(execResult.num_turns !== undefined ? { num_turns: execResult.num_turns } : {}),
      });
    } catch (e) {
      if (!(e instanceof AbortError)) {
        console.error("[scheduler] 태스크 실행 오류:", e);
      }
    } finally {
      this.processing = false;
      void this.drainScheduledQueue();
    }
  }

  /** Process any tasks that queued up while a query was in progress */
  private async drainScheduledQueue(): Promise<void> {
    const next = this.pendingScheduledTasks.shift();
    if (next) {
      console.log(`[scheduler] 큐 드레인: "${next.message.slice(0, 40)}"`);
      await this.runScheduledTask(next);
    }
  }

  private async handleInterrupt(): Promise<void> {
    console.log("[agent] 인터럽트 요청 수신");
    if (this.processing) {
      const interrupted = await this.claude.interrupt();
      if (interrupted) {
        this.send({
          type: "response",
          result: "⏹️ 작업이 중단되었습니다. 다음 메시지를 기다리는 중...",
        });
      }
    }
  }

  private async generateScreenshot(
    message: string,
    result: string,
  ): Promise<ImageData | null> {
    try {
      const projectDir = findProjectDir(
        message + "\n" + result,
        this.workDir,
      );
      if (!projectDir) return null;

      this.lastProjectPath = projectDir;
      const outputPath = getScreenshotPath();
      const screenshotPath = await screenshotProject(projectDir, outputPath);
      if (!screenshotPath) return null;

      const b64 = imageToBase64(screenshotPath);
      if (!b64) return null;

      return {
        filename: "screenshot.png",
        data: b64,
      };
    } catch (e) {
      console.error("[agent] 스크린샷 생성 실패:", e);
      return null;
    }
  }

  private async syncSession(): Promise<void> {
    const sessionId = this.claude.currentSessionId;

    this.send({
      type: "session_sync",
      work_dir: this.workDir,
      session_id: sessionId ?? null,
    });

    // Wait for session_info from server (with timeout)
    // The response is handled in handleSessionInfo
    console.log("[agent] 세션 동기화 요청 전송");
  }

  private handleSessionInfo(msg: { session_id: string | null; source: string }): void {
    if (msg.session_id && msg.source === "server") {
      // Server has a session, use it if we don't have one
      if (!this.claude.currentSessionId) {
        this.claude.currentSessionIdOverride = msg.session_id;
        saveSessionId(this.workDir, msg.session_id);
        console.log(`[agent] 서버 세션 동기화: ${msg.session_id.slice(0, 20)}...`);
      }
    }
  }

  private send(msg: AgentToServerMessage): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  private startPingLoop(): void {
    this.pingInterval = setInterval(() => {
      this.send({ type: "ping" });
    }, PING_INTERVAL_MS);
  }

  private stopPingLoop(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }
}

/**
 * Run a function (sync or async) with a timeout.
 * Returns fallback value if it times out or throws.
 */
async function withTimeout<T>(
  fn: () => T | Promise<T>,
  timeoutMs: number,
  fallback: T,
): Promise<T> {
  return new Promise<T>((resolve) => {
    const timer = setTimeout(() => resolve(fallback), timeoutMs);
    Promise.resolve()
      .then(() => fn())
      .then((result) => {
        clearTimeout(timer);
        resolve(result);
      })
      .catch(() => {
        clearTimeout(timer);
        resolve(fallback);
      });
  });
}

/** Map SDK tool names to human-readable Korean labels for the web UI */
function toolLabel(tool: string, status: "start" | "end"): string {
  const labels: Record<string, [string, string]> = {
    Read: ["📖 파일 읽는 중...", "📖 파일 읽기 완료"],
    Write: ["✏️ 파일 쓰는 중...", "✏️ 파일 쓰기 완료"],
    Edit: ["✂️ 코드 수정 중...", "✂️ 코드 수정 완료"],
    Bash: ["⚙️ 명령 실행 중...", "⚙️ 명령 실행 완료"],
    Glob: ["🔍 파일 검색 중...", "🔍 파일 검색 완료"],
    Grep: ["🔍 코드 검색 중...", "🔍 코드 검색 완료"],
    WebFetch: ["🌐 웹 요청 중...", "🌐 웹 요청 완료"],
    WebSearch: ["🌐 웹 검색 중...", "🌐 웹 검색 완료"],
    TodoWrite: ["📝 할 일 저장 중...", "📝 할 일 저장 완료"],
    NotebookEdit: ["📓 노트북 수정 중...", "📓 노트북 수정 완료"],
  };
  const pair = labels[tool];
  if (!pair) return status === "start" ? `🔧 ${tool} 실행 중...` : `🔧 ${tool} 완료`;
  return status === "start" ? pair[0] : pair[1];
}

