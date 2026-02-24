// =============================================================================
// Image data for WebSocket transport
// =============================================================================

export interface ImageData {
  filename: string;
  data: string; // base64
  mime?: string;
}

// =============================================================================
// Client -> Server (browser -> self-hosted)
// =============================================================================

export interface ClientQueryMessage {
  type: "query";
  message: string;
  model?: string;
  skill_id?: string;
  system_prompt?: string;
}

export interface ClientApprovalMessage {
  type: "approval";
  approved: boolean;
  permanent?: boolean;
}

export interface ClientInterruptMessage {
  type: "interrupt";
}

export interface ClientPingMessage {
  type: "ping";
}

export interface ClientSkillListRequest {
  type: "skill_list";
}

export interface ClientScheduleListRequest {
  type: "schedule_list";
}

export interface ClientScheduleAddRequest {
  type: "schedule_add";
  cron: string;
  message: string;
  skill_id?: string;
}

export interface ClientScheduleRemoveRequest {
  type: "schedule_remove";
  id: string;
}

export interface ClientScheduleToggleRequest {
  type: "schedule_toggle";
  id: string;
  enabled: boolean;
}

export type ClientMessage =
  | ClientQueryMessage
  | ClientApprovalMessage
  | ClientInterruptMessage
  | ClientPingMessage
  | ClientSkillListRequest
  | ClientScheduleListRequest
  | ClientScheduleAddRequest
  | ClientScheduleRemoveRequest
  | ClientScheduleToggleRequest;

// =============================================================================
// Server -> Client (self-hosted -> browser)
// =============================================================================

export interface ServerResponseMessage {
  type: "response";
  result: string;
  images?: ImageData[];
  cost_usd?: number;
  num_turns?: number;
  usage?: {
    input_tokens: number;
    output_tokens: number;
    cache_read_input_tokens: number;
    cache_creation_input_tokens: number;
  };
}

export interface ServerStreamingChunkMessage {
  type: "streaming_chunk";
  delta: string;
  index: number;
}

export interface ServerToolStatusMessage {
  type: "tool_status";
  tool: string;
  status: "start" | "end";
  label: string;
  detail?: string;
}

export interface ServerApprovalRequiredMessage {
  type: "approval_required";
  paths: string[];
  message: string;
}

export interface ServerErrorMessage {
  type: "error";
  message: string;
}

export interface ServerPongMessage {
  type: "pong";
}

export interface SkillInfo {
  id: string;
  name: string;
  icon: string;
  description: string;
}

export interface ServerSkillListResponse {
  type: "skill_list_response";
  skills: SkillInfo[];
}

export interface ServerScheduleListResponse {
  type: "schedule_list_response";
  tasks: unknown[];
}

export interface ServerScheduleAddResponse {
  type: "schedule_add_response";
  success: boolean;
  task?: unknown;
  error?: string;
}

export type ServerMessage =
  | ServerResponseMessage
  | ServerStreamingChunkMessage
  | ServerToolStatusMessage
  | ServerApprovalRequiredMessage
  | ServerErrorMessage
  | ServerPongMessage
  | ServerSkillListResponse
  | ServerScheduleListResponse
  | ServerScheduleAddResponse;
