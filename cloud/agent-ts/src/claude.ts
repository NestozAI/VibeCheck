import {
  query,
  type Query,
  type SDKMessage,
  type SDKResultSuccess,
  type SDKResultError,
  type SDKSystemMessage,
  type Options,
  AbortError,
} from "@anthropic-ai/claude-agent-sdk";

export { AbortError };
import type { SecurityManager } from "./security.js";

export interface ClaudeSessionOptions {
  workDir: string;
  sessionId: string | null;
  security: SecurityManager;
}

export class ClaudeSession {
  private currentQuery: Query | null = null;
  private abortController: AbortController | null = null;
  private sessionId: string | null;
  private sessionStarted = false;
  private workDir: string;
  private security: SecurityManager;

  /** Called when a new session ID is obtained from SDK */
  onSessionId?: (sessionId: string) => void;

  /** Called when SDKSystemMessage (init) is received */
  onSystemInit?: (msg: SDKSystemMessage) => void;

  constructor(options: ClaudeSessionOptions) {
    this.workDir = options.workDir;
    this.sessionId = options.sessionId;
    this.security = options.security;
  }

  get currentSessionId(): string | null {
    return this.sessionId;
  }

  set currentSessionIdOverride(id: string | null) {
    this.sessionId = id;
  }

  /**
   * Execute a query and return the final result text.
   * Streams SDKMessages internally; partial messages are ignored in v1.
   */
  async execute(message: string): Promise<string> {
    this.abortController = new AbortController();

    const options: Options = {
      cwd: this.workDir,
      abortController: this.abortController,
      permissionMode: "default",
      canUseTool: this.security.canUseTool,
      allowedTools: [
        "Read",
        "Write",
        "Edit",
        "Bash",
        "Glob",
        "Grep",
        "WebFetch",
        "WebSearch",
        "TodoWrite",
        "NotebookEdit",
      ],
      includePartialMessages: false, // v1: no streaming, just final messages
      env: { ...process.env, NO_COLOR: "1" },
    };

    // Session management
    if (this.sessionId) {
      options.resume = this.sessionId;
    } else if (this.sessionStarted) {
      options.continue = true;
    }

    let resultText = "";
    let newSessionId: string | null = null;

    try {
      this.currentQuery = query({ prompt: message, options });

      for await (const msg of this.currentQuery) {
        // Capture session_id from any message that has it
        if (hasSessionId(msg) && msg.session_id && !newSessionId) {
          newSessionId = msg.session_id;
        }

        switch (msg.type) {
          case "system":
            if ("subtype" in msg && msg.subtype === "init") {
              this.onSystemInit?.(msg as SDKSystemMessage);
            }
            break;

          case "result": {
            const result = msg as SDKResultSuccess | SDKResultError;
            if (result.subtype === "success") {
              resultText = (result as SDKResultSuccess).result;
            } else {
              const errorResult = result as SDKResultError;
              resultText = `오류 (${errorResult.subtype}): ${errorResult.errors?.join(", ") ?? "알 수 없는 오류"
                }`;
            }
            break;
          }

          // stream_event (partial messages), assistant, user, tool_progress etc.
          // are ignored in v1 — we only care about the final result
          default:
            break;
        }
      }
    } catch (error) {
      // AbortError는 agent.ts의 handleInterrupt가 단독으로 처리
      // → 여기서 메시지를 반환하면 handleInterrupt와 중복 전송됨
      if (error instanceof AbortError) {
        throw error;
      }

      // Invalid session → retry with new session
      const errMsg =
        error instanceof Error ? error.message : String(error);
      if (
        this.sessionId &&
        (errMsg.toLowerCase().includes("session") ||
          errMsg.toLowerCase().includes("not found"))
      ) {
        console.warn("[claude] 세션 ID가 유효하지 않음. 새 세션으로 재시도...");
        this.sessionId = null;
        this.sessionStarted = false;
        return this.execute(message);
      }

      throw error;
    } finally {
      this.currentQuery = null;
      this.abortController = null;
    }

    // Update session state
    if (!this.sessionStarted) {
      this.sessionStarted = true;
    }
    if (newSessionId && newSessionId !== this.sessionId) {
      this.sessionId = newSessionId;
      this.onSessionId?.(newSessionId);
    }

    return resultText;
  }

  /**
   * Interrupt the currently running query.
   */
  async interrupt(): Promise<boolean> {
    if (this.currentQuery) {
      try {
        await this.currentQuery.interrupt();
        return true;
      } catch (e) {
        console.error("[claude] interrupt 실패:", e);
      }
    }
    if (this.abortController) {
      this.abortController.abort();
      return true;
    }
    return false;
  }
}

function hasSessionId(msg: SDKMessage): msg is SDKMessage & { session_id: string } {
  return "session_id" in msg && typeof (msg as any).session_id === "string";
}
