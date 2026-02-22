import {
  query,
  type Query,
  type SDKMessage,
  type SDKAssistantMessage,
  type SDKPartialAssistantMessage,
  type SDKResultSuccess,
  type SDKResultError,
  type SDKSystemMessage,
  type AgentDefinition,
  type Options,
  AbortError,
} from "@anthropic-ai/claude-agent-sdk";

export { AbortError };
import type { SecurityManager } from "./security.js";
import type { Skill } from "./skills.js";
import type { AgentDef } from "./protocol.js";

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
  usage?: {
    input_tokens: number;
    output_tokens: number;
    cache_read_input_tokens: number;
    cache_creation_input_tokens: number;
  };
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

  /** Called when SDK emits a streaming text delta */
  onStreamingChunk?: (delta: string, index: number) => void;

  /** Called when Claude starts or finishes using a tool */
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
   * - Streams text chunks via onStreamingChunk (stream_event)
   * - Tool usage events via onToolStatus
   * - Skill/systemPrompt/agents applied to SDK options
   */
  async execute(
    message: string,
    model?: string,
    skill?: Skill,
    systemPrompt?: string,
    agents?: Record<string, AgentDef>,
  ): Promise<ExecuteResult> {
    this.abortController = new AbortController();

    const globalAllowedTools = [
      "Read", "Write", "Edit", "Bash", "Glob", "Grep",
      "WebFetch", "WebSearch", "TodoWrite", "NotebookEdit",
    ];

    // Build systemPrompt option: prefer skill, fallback to per-query prompt
    const skillPrompt = skill?.systemPrompt;
    const combinedPrompt = [skillPrompt, systemPrompt].filter(Boolean).join("\n\n");

    // Convert AgentDef → SDK AgentDefinition
    const sdkAgents: Record<string, AgentDefinition> | undefined = agents
      ? Object.fromEntries(
        Object.entries(agents).map(([name, def]) => [
          name,
          {
            description: def.description,
            prompt: def.prompt,
            ...(def.tools ? { tools: def.tools } : {}),
            ...(def.disallowedTools ? { disallowedTools: def.disallowedTools } : {}),
          } satisfies AgentDefinition,
        ]),
      )
      : undefined;

    const options: Options = {
      cwd: this.workDir,
      abortController: this.abortController,
      permissionMode: "default",
      canUseTool: this.security.canUseTool,
      allowedTools: skill?.allowedTools ?? globalAllowedTools,
      includePartialMessages: true, // emit stream_event for real-time chunks
      env: { ...process.env, NO_COLOR: "1" },
      ...(model ? { model } : {}),
      ...(combinedPrompt
        ? { systemPrompt: { type: "preset" as const, preset: "claude_code" as const, append: combinedPrompt } }
        : {}),
      ...(sdkAgents ? { agents: sdkAgents } : {}),
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
    let usage: ExecuteResult["usage"] | undefined;
    let newSessionId: string | null = null;
    // Maps tool_use id → tool name for correct end-event names
    const toolUseIdMap = new Map<string, string>();
    let chunkIndex = 0;

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

          // ── Streaming text delta ──────────────────────────────────────────
          case "stream_event": {
            const partial = msg as SDKPartialAssistantMessage;
            const event = partial.event as any;
            // content_block_delta carries text deltas
            if (
              event?.type === "content_block_delta" &&
              event?.delta?.type === "text_delta" &&
              typeof event?.delta?.text === "string"
            ) {
              this.onStreamingChunk?.(event.delta.text, chunkIndex++);
            }
            break;
          }

          // ── Tool start ───────────────────────────────────────────────────
          case "assistant": {
            const assistantMsg = msg as SDKAssistantMessage;
            const content = assistantMsg.message?.content;
            if (Array.isArray(content)) {
              for (const block of content) {
                if (block.type === "tool_use") {
                  toolUseIdMap.set(block.id, block.name);
                  const detail = extractToolDetail(
                    block.name,
                    block.input as Record<string, unknown>,
                  );
                  this.onToolStatus?.(block.name, "start", detail);
                }
              }
            }
            break;
          }

          // ── Tool end ─────────────────────────────────────────────────────
          case "user": {
            const userContent = (msg as any).message?.content;
            if (Array.isArray(userContent)) {
              for (const block of userContent) {
                if (block.type === "tool_result") {
                  const toolName = toolUseIdMap.get(block.tool_use_id) ?? "tool";
                  this.onToolStatus?.(toolName, "end");
                }
              }
            }
            break;
          }

          // ── Final result ─────────────────────────────────────────────────
          case "result": {
            const result = msg as SDKResultSuccess | SDKResultError;
            num_turns = result.num_turns;
            if (result.subtype === "success") {
              const success = result as SDKResultSuccess;
              resultText = success.result;
              cost_usd = success.total_cost_usd;
              // Extract token usage breakdown
              if (success.usage) {
                const u = success.usage as any;
                usage = {
                  input_tokens: u.input_tokens ?? 0,
                  output_tokens: u.output_tokens ?? 0,
                  cache_read_input_tokens: u.cache_read_input_tokens ?? 0,
                  cache_creation_input_tokens: u.cache_creation_input_tokens ?? 0,
                };
              }
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
      // AbortError는 handleInterrupt가 단독으로 처리
      if (error instanceof AbortError) throw error;

      // Invalid session → retry with new session
      const errMsg = error instanceof Error ? error.message : String(error);
      if (
        this.sessionId &&
        (errMsg.toLowerCase().includes("session") ||
          errMsg.toLowerCase().includes("not found"))
      ) {
        console.warn("[claude] 세션 ID가 유효하지 않음. 새 세션으로 재시도...");
        this.sessionId = null;
        this.sessionStarted = false;
        return this.execute(message, model, skill, systemPrompt, agents);
      }

      throw error;
    } finally {
      this.currentQuery = null;
      this.abortController = null;
    }

    // Update session state
    if (!this.sessionStarted) this.sessionStarted = true;
    if (newSessionId && newSessionId !== this.sessionId) {
      this.sessionId = newSessionId;
      this.onSessionId?.(newSessionId);
    }

    return { text: resultText, cost_usd, num_turns, usage };
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
