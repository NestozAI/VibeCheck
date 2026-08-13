/**
 * Effect log — JSONL log_stream (effects.manifest.json의 log_stream 필드가 가리키는 곳).
 *
 * 이 모듈이 effect 로그 파일 쓰기의 유일한 choke point다.
 * recon(scripts/recon-effects.mjs)은 이 파일들을 per-trigger로 대사한다:
 * 모든 `trigger` 레코드는 유예시간 내에 터미널 결과(sent|skipped|failed)를
 * 가져야 한다. `queued`는 pending(유예 내 정상)으로 취급된다.
 */

import { appendFileSync, existsSync, mkdirSync } from "node:fs";
import os from "node:os";
import path from "node:path";

export type EffectOutcome = "trigger" | "sent" | "queued" | "skipped" | "failed";

export interface EffectEvent {
  /** effects.manifest.json의 effect id */
  effect: "ws-uplink" | "approval-gate" | "screenshot";
  trigger_id: string;
  outcome: EffectOutcome;
  /** skipped/failed/queued일 때 필수 — fall-through 금지 (playbook 원칙 0) */
  reason?: string;
  detail?: string;
}

export function effectLogDir(): string {
  return (
    process.env.VIBECHECK_LOG_DIR || path.join(os.homedir(), ".vibecheck", "logs")
  );
}

export function logEffect(ev: EffectEvent): void {
  try {
    const dir = effectLogDir();
    if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
    const day = new Date().toISOString().slice(0, 10);
    const file = path.join(dir, `effects-${day}.jsonl`);
    appendFileSync(
      file,
      JSON.stringify({ ts: new Date().toISOString(), ...ev }) + "\n",
    );
  } catch (e) {
    // 로깅 실패가 본 기능을 막으면 안 되지만, 침묵도 금지 — 콘솔에는 남긴다
    console.warn(
      "[effects] effect log write failed:",
      e instanceof Error ? e.message : e,
    );
  }
}
