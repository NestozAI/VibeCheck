import {
  query,
  type Query,
  type SDKMessage,
  type SDKAssistantMessage,
  type SDKResultSuccess,
  type SDKResultError,
  type SDKSystemMessage,
  type Options,
  AbortError,
} from "@anthropic-ai/claude-agent-sdk";

export { AbortError };
import type { SecurityManager } from "./security.js";
import type { Skill } from "./skills.js";

export interface ClaudeSessionOptions {
  workDir: string;
  sessionId: string | null;
  security: SecurityManager;
}

/** Result returned from execute() — text + metadata */
export interface ExecuteResult {
  text: string;
  cost_usd?: number;
  num_turns?: number;
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

  /**
   * Called when Claude starts or finishes using a tool.
   * Lets agent.ts forward tool_status messages to the web UI.
   */
  onToolStatus?: (tool: string, status: "start" | "end", detail?: string) => void;

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
   * Execute a query and return the result with metadata.
   * Tool usage events are emitted via onToolStatus as they happen.
   * Skill preset (if provided) overrides systemPrompt and allowedTools.
   */
  async execute(message: string, model?: string, skill?: Skill): Promise<ExecuteResult> {
    this.abortController = new AbortController();

    const globalAllowedTools = [
      "Read", "Write", "Edit", "Bash", "Glob", "Grep",
      "WebFetch", "WebSearch", "TodoWrite", "NotebookEdit",
    ];

    const options: Options = {
      cwd: this.workDir,
      abortController: this.abortController,
      permissionMode: "default",
      canUseTool: this.security.canUseTool,
      allowedTools: skill?.allowedTools ?? globalAllowedTools,
      includePartialMessages: false, // v1: no streaming, just final messages
      env: { ...process.env, NO_COLOR: "1" },
      ...(model ? { model } : {}),
      // Skill system prompt: append to Claude's default system prompt
      ...(skill?.systemPrompt
        ? { systemPrompt: { type: "preset" as const, preset: "claude_code" as const, append: skill.systemPrompt } }
        : {}),
    };

    // Session management
    if (this.sessionId) {
      options.resume = this.sessionId;
    } else if (this.sessionStarted) {
      options.continue = true;
    }

    let resultText = "";
    let cost_usd: number | undefined;
    let num_turns: number | undefined;
    let newSessionId: string | null = null;
    // Maps tool_use id → tool name, used to emit the correct name on tool_result
    const toolUseIdMap = new Map<string, string>();

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

          case "assistant": {
            // Detect tool_use blocks → emit tool status events
            const assistantMsg = msg as SDKAssistantMessage;
            const content = assistantMsg.message?.content;
            if (Array.isArray(content)) {
              for (const block of content) {
                if (block.type === "tool_use") {
                  // Remember id → name for when tool_result arrives
                  toolUseIdMap.set(block.id, block.name);
                  const detail = extractToolDetail(block.name, block.input as Record<string, unknown>);
                  this.onToolStatus?.(block.name, "start", detail);
                }
              }
            }
            break;
          }

          case "user": {
            // tool_result blocks signal a tool finished execution
            const userContent = (msg as any).message?.content;
            if (Array.isArray(userContent)) {
              for (const block of userContent) {
                if (block.type === "tool_result") {
                  // Look up the actual tool name from the tool_use_id
                  const toolName = toolUseIdMap.get(block.tool_use_id) ?? "tool";
                  this.onToolStatus?.(toolName, "end");
                }
              }
            }
            break;
          }

          case "result": {
            const result = msg as SDKResultSuccess | SDKResultError;
            num_turns = result.num_turns;
            if (result.subtype === "success") {
              const success = result as SDKResultSuccess;
              resultText = success.result;
              cost_usd = success.total_cost_usd;
            } else {
              const errorResult = result as SDKResultError;
              cost_usd = errorResult.total_cost_usd;
              resultText = `오류 (${errorResult.subtype}): ${errorResult.errors?.join(", ") ?? "알 수 없는 오류"
                }`;
            }
            break;
          }

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
        return this.execute(message, model, skill);
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

    return { text: resultText, cost_usd, num_turns };
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

/** Extract a short human-readable detail from a tool input */
function extractToolDetail(
  toolName: string,
  input: Record<string, unknown>,
): string | undefined {
  switch (toolName) {
    case "Read":
    case "Write":
    case "Edit":
      return typeof input.file_path === "string" ? input.file_path : undefined;
    case "Bash":
      return typeof input.command === "string"
        ? input.command.slice(0, 80)
        : undefined;
    case "Glob":
    case "Grep":
      return typeof input.pattern === "string" ? input.pattern : undefined;
    case "WebFetch":
    case "WebSearch":
      return typeof input.url === "string"
        ? input.url
        : typeof input.query === "string"
          ? input.query
          : undefined;
    default:
      return undefined;
  }
}
