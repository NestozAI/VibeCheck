// WebSocket message types for VibeCheck Agent <-> Server protocol

// === Shared types ===

export interface ImageData {
  filename: string;
  data: string; // base64
}

// === Agent -> Server messages ===

export interface PingMessage {
  type: "ping";
}

export interface PongMessage {
  type: "pong";
}

export interface ResponseMessage {
  type: "response";
  result: string;
  images?: ImageData[];
  /** Total cost in USD for this query (from SDKResultMessage) */
  cost_usd?: number;
  /** Number of agentic turns used */
  num_turns?: number;
}

export interface ApprovalRequiredMessage {
  type: "approval_required";
  paths: string[];
  message: string;
}

export interface SessionSyncMessage {
  type: "session_sync";
  work_dir: string;
  session_id: string | null;
}

export interface SessionUpdateMessage {
  type: "session_update";
  work_dir: string;
  session_id: string;
}

/**
 * Real-time tool usage status — sent while Claude is actively using a tool.
 * Lets the web UI show "파일 읽는 중...", "코드 수정 중..." etc.
 */
export interface ToolStatusMessage {
  type: "tool_status";
  tool: string;       // e.g. "Read", "Write", "Bash"
  status: "start" | "end";
  /** Human-readable label for the web UI */
  label: string;
  /** Optional detail (file path, command snippet, ...) */
  detail?: string;
}

export type AgentToServerMessage =
  | PingMessage
  | PongMessage
  | ResponseMessage
  | ApprovalRequiredMessage
  | SessionSyncMessage
  | SessionUpdateMessage
  | ToolStatusMessage;

// === Server -> Agent messages ===

export interface QueryMessage {
  type: "query";
  message: string;
  /** Optional model override. Defaults to Claude's configured model. */
  model?: string;
}

export interface ApprovalMessage {
  type: "approval";
  approved: boolean;
  permanent?: boolean;
}

export interface AddTrustedPathMessage {
  type: "add_trusted_path";
  path: string;
}

export interface InterruptMessage {
  type: "interrupt";
}

export interface SessionInfoMessage {
  type: "session_info";
  session_id: string | null;
  source: "server" | "agent";
}

export interface ErrorMessage {
  type: "error";
  message: string;
}

export type ServerToAgentMessage =
  | QueryMessage
  | ApprovalMessage
  | AddTrustedPathMessage
  | InterruptMessage
  | PingMessage
  | PongMessage
  | ErrorMessage
  | SessionInfoMessage;

