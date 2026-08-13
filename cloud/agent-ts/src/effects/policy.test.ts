/**
 * 매트릭스 완전성 테스트 (playbook 원칙 3).
 *
 * MATRIX가 "누가 언제 무엇을 받는가"의 단일 진실이다. 각 행은 차원 조합에
 * 대한 기대 결과이고, 크로스 프로덕트 테스트가 모든 조합에 행이 존재함을
 * 강제한다 — "이 조합의 행이 없네?"가 사람 눈이 아니라 테스트 실패로
 * 드러난다. 차원을 추가/변경하면 이 파일이 깨지는 것이 정상이다.
 *
 * 실행: cd cloud/agent-ts && npm test
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  DIMENSIONS,
  resolveDelivery,
  resolvePermissionGate,
  resolveApprovalReply,
  resolveScreenshot,
  type DeliveryDecision,
  type GateDecision,
  type ApprovalDecision,
  type ScreenshotDecision,
} from "./policy.js";

/** 차원 값 배열들의 크로스 프로덕트 */
function cartesian<T extends Record<string, readonly string[]>>(
  dims: T,
): Array<{ [K in keyof T]: T[K][number] }> {
  return Object.entries(dims).reduce<Array<Record<string, string>>>(
    (acc, [key, values]) =>
      acc.flatMap((combo) => values.map((v) => ({ ...combo, [key]: v }))),
    [{}],
  ) as Array<{ [K in keyof T]: T[K][number] }>;
}

/** 행의 명시된 차원만 비교 (미명시 = 와일드카드). 먼저 매칭되는 행이 이긴다. */
function findRow<R extends { when: Record<string, string> }>(
  rows: R[],
  combo: Record<string, string>,
): R | undefined {
  return rows.find((r) =>
    Object.entries(r.when).every(([k, v]) => combo[k] === v),
  );
}

// ── 정책 1: 업링크 전달 ────────────────────────────────────────────────────
// 차원: uplinkClass × wsState × source × plan (source·plan은 선언적 — 전 값 동일)

const DELIVERY_MATRIX: Array<{
  name: string;
  when: Partial<Record<"cls" | "ws" | "source" | "plan", string>>;
  expect: DeliveryDecision;
}> = [
  {
    name: "연결 열림 → 무조건 즉시 전송 (출처·플랜 무관)",
    when: { ws: "open" },
    expect: { kind: "send" },
  },
  {
    name: "연결 닫힘 + durable(response/approval) → 큐잉 후 재접속 시 전송 (B1 수정)",
    when: { ws: "closed", cls: "durable" },
    expect: { kind: "queue", reason: "ws-closed" },
  },
  {
    name: "연결 닫힘 + heartbeat → skip(reason)",
    when: { ws: "closed", cls: "heartbeat" },
    expect: { kind: "skip", reason: "heartbeat-while-closed" },
  },
  {
    name: "연결 닫힘 + ephemeral(스트림·조회 응답) → skip(reason)",
    when: { ws: "closed", cls: "ephemeral" },
    expect: { kind: "skip", reason: "ws-closed-ephemeral" },
  },
];

for (const combo of cartesian({
  cls: DIMENSIONS.uplinkClass,
  ws: DIMENSIONS.wsState,
  source: DIMENSIONS.source,
  plan: DIMENSIONS.plan,
})) {
  test(`delivery coverage: ${JSON.stringify(combo)}`, () => {
    const row = findRow(DELIVERY_MATRIX, combo);
    assert.ok(row, `MATRIX에 이 조합의 행이 없다: ${JSON.stringify(combo)}`);
    assert.deepEqual(
      resolveDelivery({
        cls: combo.cls,
        ws: combo.ws,
        source: combo.source,
        plan: combo.plan,
      }),
      row.expect,
      row.name,
    );
  });
}

// ── 정책 2: 권한 게이트 ────────────────────────────────────────────────────

const GATE_MATRIX: Array<{
  name: string;
  when: Partial<Record<"trust" | "tool", string>>;
  expect: GateDecision;
}> = [
  {
    name: "모든 경로 신뢰됨 → 즉시 허용",
    when: { trust: "trusted" },
    expect: { kind: "allow" },
  },
  {
    name: "비신뢰 경로 + 안전 명령(read-only bash) → 허용",
    when: { trust: "untrusted", tool: "safe-bash" },
    expect: { kind: "allow" },
  },
  {
    name: "비신뢰 경로 + 그 외 도구 → 사용자 승인 요청",
    when: { trust: "untrusted", tool: "other" },
    expect: { kind: "ask" },
  },
];

for (const combo of cartesian({
  trust: DIMENSIONS.pathTrust,
  tool: DIMENSIONS.toolClass,
})) {
  test(`gate coverage: ${JSON.stringify(combo)}`, () => {
    const row = findRow(GATE_MATRIX, combo);
    assert.ok(row, `MATRIX에 이 조합의 행이 없다: ${JSON.stringify(combo)}`);
    assert.deepEqual(
      resolvePermissionGate({ trust: combo.trust, tool: combo.tool }),
      row.expect,
      row.name,
    );
  });
}

// ── 정책 2b: 승인 응답 ─────────────────────────────────────────────────────

const REPLY_MATRIX: Array<{
  name: string;
  when: { reply: string };
  expect: ApprovalDecision;
}> = [
  {
    name: "1회 허용",
    when: { reply: "allow" },
    expect: { kind: "allow", persist: false },
  },
  {
    name: "영구 허용 → trusted path 등록",
    when: { reply: "allow-permanent" },
    expect: { kind: "allow", persist: true },
  },
  {
    name: "거부",
    when: { reply: "deny" },
    expect: { kind: "deny", reason: "user-denied" },
  },
  {
    name: "쿼리 중단으로 승인 무효화",
    when: { reply: "abort" },
    expect: { kind: "deny", reason: "operation-aborted" },
  },
  {
    name: "응답 없음 → 타임아웃 deny (B2 수정: 무한 대기 금지)",
    when: { reply: "timeout" },
    expect: { kind: "deny", reason: "approval-timeout" },
  },
];

for (const combo of cartesian({ reply: DIMENSIONS.approvalReply })) {
  test(`approval-reply coverage: ${JSON.stringify(combo)}`, () => {
    const row = findRow(REPLY_MATRIX, combo);
    assert.ok(row, `MATRIX에 이 조합의 행이 없다: ${JSON.stringify(combo)}`);
    assert.deepEqual(resolveApprovalReply(combo.reply), row.expect, row.name);
  });
}

// ── 정책 3: 프리뷰 스크린샷 ────────────────────────────────────────────────

const SCREENSHOT_MATRIX: Array<{
  name: string;
  when: { target: string };
  expect: ScreenshotDecision;
}> = [
  {
    name: "웹 프로젝트 발견 → 시도 (런타임 실패는 skipped(reason)으로 로깅)",
    when: { target: "found" },
    expect: { kind: "attempt" },
  },
  {
    name: "웹 프로젝트 없음 → skip + 응답에 사유 표기 (B3 수정)",
    when: { target: "none" },
    expect: { kind: "skip", reason: "no-web-project" },
  },
];

for (const combo of cartesian({ target: DIMENSIONS.screenshotTarget })) {
  test(`screenshot coverage: ${JSON.stringify(combo)}`, () => {
    const row = findRow(SCREENSHOT_MATRIX, combo);
    assert.ok(row, `MATRIX에 이 조합의 행이 없다: ${JSON.stringify(combo)}`);
    assert.deepEqual(resolveScreenshot({ target: combo.target }), row.expect, row.name);
  });
}
