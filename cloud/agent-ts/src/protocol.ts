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
  /** Token usage breakdown */
  usage?: {
    input_tokens: number;
    output_tokens: number;
    cache_read_input_tokens: number;
    cache_creation_input_tokens: number;
  };
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
  hostname?: string;
}

export interface SessionUpdateMessage {
  type: "session_update";
  work_dir: string;
  session_id: string;
}

/**
 * Real-time tool usage status — sent while Claude is actively using a tool.
 * Lets the web UI show "Reading file...", "Editing code..." etc.
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

/**
 * Real-time streaming chunk — emitted for each text delta while Claude is generating.
 * Web UI can use these to show a typing animation before the final response arrives.
 * The final `response` message is always sent at the end (backwards-compatible).
 */
export interface StreamingChunkMessage {
  type: "streaming_chunk";
  delta: string;    // incremental text
  index: number;   // sequence number within this response
}

/**
 * Claude Code local session info — scanned from ~/.claude/projects/
 */
export interface ClaudeCodeSessionInfo {
  sessionId: string;
  firstPrompt: string;
  messageCount: number;
  created: string;
  modified: string;
  gitBranch?: string;
  projectPath: string;
  /** Whether the session has displayable conversation content */
  hasConversation?: boolean;
}

export interface ClaudeSessionsMessage {
  type: "claude_sessions";
  sessions: ClaudeCodeSessionInfo[];
}

export interface SessionHistoryMessage {
  type: "session_history";
  session_id: string;
  history: { role: "user" | "assistant"; content: string }[];
}

/** Lightweight project summary for discovery */
export interface ProjectSummaryInfo {
  projectPath: string;
  dirName: string;
  sessionCount: number;
  lastModified: string;
}

/** Agent → Server: list of all discoverable projects */
export interface ProjectListMessage {
  type: "project_list";
  projects: ProjectSummaryInfo[];
}

/** Agent → Server: sessions for a specific project (after user selects one) */
export interface ProjectSessionsMessage {
  type: "project_sessions";
  projectPath: string;
  sessions: ClaudeCodeSessionInfo[];
}

export type AgentToServerMessage =
  | PingMessage
  | PongMessage
  | ResponseMessage
  | ApprovalRequiredMessage
  | SessionSyncMessage
  | SessionUpdateMessage
  | ToolStatusMessage
  | StreamingChunkMessage
  | SkillListResponseMessage
  | ScheduleListResponseMessage
  | ScheduleAddResponseMessage
  | ClaudeSessionsMessage
  | SessionHistoryMessage
  | ProjectListMessage
  | ProjectSessionsMessage;

// === Server -> Agent messages ===

/** Definition of a custom sub-agent for multi-agent workflows */
export interface AgentDef {
  description: string;
  prompt: string;
  tools?: string[];
  disallowedTools?: string[];
}

export interface QueryMessage {
  type: "query";
  message: string;
  /** Optional model override. Defaults to Claude's configured model. */
  model?: string;
  /** Optional skill preset ID (e.g. "code-review", "research"). */
  skill_id?: string;
  /**
   * Custom system prompt injected for this query only.
   * Appended after any skill systemPrompt.
   */
  system_prompt?: string;
  /**
   * Custom sub-agents for multi-agent workflows.
   * Keys are agent names; Claude can invoke them via the Task tool.
   */
  agents?: Record<string, AgentDef>;
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

// === Skill messages (Server -> Agent) ===

export interface SkillListRequestMessage {
  type: "skill_list";
}

// === Schedule messages (Server -> Agent) ===

export interface ScheduleAddMessage {
  type: "schedule_add";
  cron: string;
  message: string;
  skill_id?: string;
}

export interface ScheduleRemoveMessage {
  type: "schedule_remove";
  id: string;
}

export interface ScheduleToggleMessage {
  type: "schedule_toggle";
  id: string;
  enabled: boolean;
}

export interface ScheduleListRequestMessage {
  type: "schedule_list";
}

export interface ResumeSessionMessage {
  type: "resume_session";
  session_id: string;
  /** Project path for cross-project session resume (from Browse Projects) */
  projectPath?: string;
}

/** Server → Agent: request list of all discoverable projects */
export interface DiscoverProjectsMessage {
  type: "discover_projects";
}

/** Server → Agent: request sessions for a specific project path */
export interface ScanProjectMessage {
  type: "scan_project";
  projectPath: string;
}

export type ServerToAgentMessage =
  | QueryMessage
  | ApprovalMessage
  | AddTrustedPathMessage
  | InterruptMessage
  | PingMessage
  | PongMessage
  | ErrorMessage
  | SessionInfoMessage
  | SkillListRequestMessage
  | ScheduleAddMessage
  | ScheduleRemoveMessage
  | ScheduleToggleMessage
  | ScheduleListRequestMessage
  | ResumeSessionMessage
  | DiscoverProjectsMessage
  | ScanProjectMessage;

// === Skill / Schedule response messages (Agent -> Server) ===

export interface SkillInfo {
  id: string;
  name: string;
  icon: string;
  description: string;
}

export interface SkillListResponseMessage {
  type: "skill_list_response";
  skills: SkillInfo[];
}

export interface ScheduleTaskInfo {
  id: string;
  cron: string;
  message: string;
  skill_id?: string;
  enabled: boolean;
  created_at: string;
  last_run?: string;
  last_result?: string;
}

export interface ScheduleListResponseMessage {
  type: "schedule_list_response";
  tasks: ScheduleTaskInfo[];
}

export interface ScheduleAddResponseMessage {
  type: "schedule_add_response";
  success: boolean;
  task?: ScheduleTaskInfo;
  error?: string;
}

