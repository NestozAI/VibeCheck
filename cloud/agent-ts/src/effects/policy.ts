/**
 * Side-effect 정책 함수 (side-effect-invariants-playbook 원칙 1).
 *
 * 트리거→효과 경로의 분기 결정은 전부 이 파일의 순수 함수 안에서만 한다.
 * 호출부(if)에 분기를 새로 만들지 말 것 — 새 분기 조건은 여기의 입력
 * 차원으로 승격하고, policy.test.ts의 MATRIX에 새 조합 전체의 행을 추가한다.
 * 입력은 닫힌 union이므로 케이스 누락은 런타임 침묵이 아니라 컴파일 에러다.
 */

import type { AgentToServerMessage } from "../protocol.js";

// ── 차원 (닫힌 union) ──────────────────────────────────────────────────────
// 값 목록은 완전성 테스트(policy.test.ts)가 크로스 프로덕트 생성에 사용한다.

export const DIMENSIONS = {
  uplinkClass: ["durable", "ephemeral", "heartbeat"],
  wsState: ["open", "closed"],
  /** 쿼리 유입 출처 — 사용자 확인으로 승격된 차원 (2026-08-10). 현재 동작 무차별. */
  source: ["web", "slack", "schedule"],
  /** 플랜 — 사용자 확인으로 승격된 선언적 차원. agent에는 아직 분기 없음.
   *  플랜별 동작을 도입하려면 resolveDelivery에 분기를 넣고 MATRIX를 갱신할 것. */
  plan: ["free", "pro"],
  pathTrust: ["trusted", "untrusted"],
  toolClass: ["safe-bash", "other"],
  approvalReply: ["allow", "allow-permanent", "deny", "abort", "timeout"],
  screenshotTarget: ["found", "none"],
} as const;

export type UplinkClass = (typeof DIMENSIONS.uplinkClass)[number];
export type WsState = (typeof DIMENSIONS.wsState)[number];
export type QuerySource = (typeof DIMENSIONS.source)[number];
export type Plan = (typeof DIMENSIONS.plan)[number];
export type PathTrust = (typeof DIMENSIONS.pathTrust)[number];
export type ToolClass = (typeof DIMENSIONS.toolClass)[number];
export type ApprovalReply = (typeof DIMENSIONS.approvalReply)[number];
export type ScreenshotTarget = (typeof DIMENSIONS.screenshotTarget)[number];

export function assertNever(x: never): never {
  throw new Error(`Unhandled case: ${JSON.stringify(x)}`);
}

// ── 업링크 메시지 등급 ─────────────────────────────────────────────────────
// Record가 exhaustive이므로 protocol.ts에 메시지 타입이 추가되면 컴파일 에러.
// durable  = 유저에게 반드시 도달해야 하는 결과 → ws 닫힘 시 큐잉 후 재전송
// ephemeral = 실시간에만 의미 있는 스트림/조회 응답 → 닫힘 시 skip(reason)
// heartbeat = 연결 유지 신호 → 닫힘 시 skip(reason)

const UPLINK_CLASS: Record<AgentToServerMessage["type"], UplinkClass> = {
  ping: "heartbeat",
  pong: "heartbeat",
  response: "durable",
  approval_required: "durable",
  session_sync: "ephemeral",
  session_update: "ephemeral",
  tool_status: "ephemeral",
  streaming_chunk: "ephemeral",
  skill_list_response: "ephemeral",
  schedule_list_response: "ephemeral",
  schedule_add_response: "ephemeral",
  claude_sessions: "ephemeral",
  session_history: "ephemeral",
  project_list: "ephemeral",
  project_sessions: "ephemeral",
};

export function classifyUplink(t: AgentToServerMessage["type"]): UplinkClass {
  return UPLINK_CLASS[t];
}

// ── 정책 1: 업링크 전달 (effect: ws-uplink) ────────────────────────────────

export interface DeliveryContext {
  cls: UplinkClass;
  ws: WsState;
  source: QuerySource;
  plan: Plan;
}

export type DeliveryDecision =
  | { kind: "send" }
  | { kind: "queue"; reason: "ws-closed" }
  | { kind: "skip"; reason: "heartbeat-while-closed" | "ws-closed-ephemeral" };

export function resolveDelivery(ctx: DeliveryContext): DeliveryDecision {
  // source·plan은 현재 모든 값에서 동작이 동일한 선언적 차원이다.
  if (ctx.ws === "open") return { kind: "send" };
  switch (ctx.cls) {
    case "durable":
      return { kind: "queue", reason: "ws-closed" };
    case "heartbeat":
      return { kind: "skip", reason: "heartbeat-while-closed" };
    case "ephemeral":
      return { kind: "skip", reason: "ws-closed-ephemeral" };
    default:
      return assertNever(ctx.cls);
  }
}

// ── 정책 2: 권한 게이트 (effect: approval-gate) ────────────────────────────

export interface GateContext {
  trust: PathTrust;
  tool: ToolClass;
}

export type GateDecision = { kind: "allow" } | { kind: "ask" };

export function resolvePermissionGate(ctx: GateContext): GateDecision {
  if (ctx.trust === "trusted") return { kind: "allow" };
  if (ctx.tool === "safe-bash") return { kind: "allow" };
  return { kind: "ask" };
}

/** 승인 응답이 이 시간 내에 없으면 timeout으로 deny된다 (무한 대기 금지) */
export const APPROVAL_TIMEOUT_MS = 10 * 60_000;

export type ApprovalDecision =
  | { kind: "allow"; persist: boolean }
  | {
      kind: "deny";
      reason: "user-denied" | "operation-aborted" | "approval-timeout";
    };

export function resolveApprovalReply(reply: ApprovalReply): ApprovalDecision {
  switch (reply) {
    case "allow":
      return { kind: "allow", persist: false };
    case "allow-permanent":
      return { kind: "allow", persist: true };
    case "deny":
      return { kind: "deny", reason: "user-denied" };
    case "abort":
      return { kind: "deny", reason: "operation-aborted" };
    case "timeout":
      return { kind: "deny", reason: "approval-timeout" };
    default:
      return assertNever(reply);
  }
}

// ── 정책 3: 프리뷰 스크린샷 (effect: screenshot) ───────────────────────────

export type ScreenshotDecision =
  | { kind: "attempt" }
  | { kind: "skip"; reason: "no-web-project" };

export function resolveScreenshot(ctx: {
  target: ScreenshotTarget;
}): ScreenshotDecision {
  switch (ctx.target) {
    case "found":
      return { kind: "attempt" };
    case "none":
      return { kind: "skip", reason: "no-web-project" };
    default:
      return assertNever(ctx.target);
  }
}
