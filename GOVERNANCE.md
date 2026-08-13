# Effect Governance — VibeCheck (agent + self-hosted)

규격 v1 기준 (`~/.claude/effect-governance.md` + `side-effect-invariants-playbook.md`)
의 이 리포 맞춤판. **적용 티어: small** (스캐너 + 매니페스트 + 완전성 테스트 +
per-trigger recon. Layer 4 런타임 가드는 미적용). 일반론은 규격 문서를 참조하고,
이 문서는 이 리포의 실제 경로·패턴·차원만 담는다.

단일 진실:
- 출구 레지스트리 → [effects.manifest.json](./effects.manifest.json)
- 분기 정책(순수 함수) → [cloud/agent-ts/src/effects/policy.ts](./cloud/agent-ts/src/effects/policy.ts)
- 매트릭스(테스트 데이터) → [cloud/agent-ts/src/effects/policy.test.ts](./cloud/agent-ts/src/effects/policy.test.ts)
- effect 로그 choke → [cloud/agent-ts/src/effects/log.ts](./cloud/agent-ts/src/effects/log.ts)

검증 명령 (완료 선언 전 필수, exit 0이 아니면 완료가 아니다):

```bash
node scripts/scan-effects.mjs          # 존재 계층: 미등록/경계 밖 출구 탐지
cd cloud/agent-ts && npm test          # 커버리지 계층: 매트릭스 완전성 (47 tests)
node scripts/recon-effects.mjs         # 배포 후: per-trigger 대사
```

## 이 리포의 출구 지도 (Exit Taxonomy 번역)

| effect id | 카테고리 | 실체 | choke point |
|---|---|---|---|
| `ws-uplink` | network | agent↔서버 WebSocket (응답·승인요청 전달) | `agent.ts#send` → `resolveDelivery` |
| `claude-query` | sdk | Claude Agent SDK `query()` — **위임 효과 전체**(파일·명령·API) | `claude.ts#execute` (경계는 approval-gate) |
| `approval-gate` | messaging | 비신뢰 경로 도구 사용 승인 요청/결정 | `security.ts#canUseTool→settleApproval` |
| `slack-notify` | sdk | Slack Bolt 발송 (self-hosted 옵션) | `slack/handler.ts` |
| `self-update` | process | `npm view/install -g` 자가 업데이트 | `updater.ts#checkForUpdates` |
| `self-restart` | process | 자기 자신 spawn 재시작 | `index.ts` |
| `preview-screenshot` | process | ⚠ 유저 프로젝트 `npm install` + dev 서버 spawn + chromium | `screenshot.ts#screenshotProject` |
| `local-state` | filesystem | 세션맵·스케줄·effect 로그·임시 이미지 (wrapper funnel) | session/scheduler/effects·log/agent |
| `ops-restart` | process | health-check cron의 systemctl restart | `scripts/health-check.sh` |

해당 없음(현재): storage(DB), 큐/pub-sub, 결제 SDK — 새로 생기면 이 표와
매니페스트에 **코드보다 먼저** 등록한다.

**탐지 축은 import + 클라이언트 생성자다.** 메서드명 grep 금지 — 이 리포에서
`.exec(` grep은 전부 `RegExp.exec()` 오탐이었다 (실측). fs write만 예외적으로
"node:fs를 import한 파일 내 write 호출명" 2단 탐지를 쓴다.

## 차원과 매트릭스 (커버리지 계층)

트리거→효과 경로의 분기 조건은 전부 `policy.ts`의 입력 차원으로 승격돼 있다
(닫힌 union — 케이스 누락은 컴파일 에러). 호출부에 if를 새로 만들지 말 것.

| 정책 | 차원 | 값 |
|---|---|---|
| `resolveDelivery` | uplinkClass × wsState × source × plan | durable/ephemeral/heartbeat × open/closed × web/slack/schedule × free/pro |
| `resolvePermissionGate` | pathTrust × toolClass | trusted/untrusted × safe-bash/other |
| `resolveApprovalReply` | approvalReply | allow/allow-permanent/deny/abort/**timeout** |
| `resolveScreenshot` | screenshotTarget | found/none |

- `source`·`plan`은 2026-08-11 사용자 확인으로 승격된 **선언적 차원** — 현재 전
  값에서 동작이 동일하다. 플랜별/출처별 동작을 도입하는 순간 매트릭스 갱신이
  강제된다. 멀티 에이전트(한 키에 여러 대)는 서버 레포의 차원이다 (agent
  프로세스는 단일) — 서버 레포 GOVERNANCE.md가 소유.
- protocol.ts에 agent→서버 메시지 타입을 추가하면 `policy.ts`의 `UPLINK_CLASS`
  Record가 컴파일 에러를 낸다 — durable/ephemeral/heartbeat 등급을 정하고
  매트릭스를 확인한 뒤 통과시킬 것.

### 매트릭스가 기록한 의도 (수정 이력 포함)

| 조합 | 결과 | 비고 |
|---|---|---|
| ws open × 전 메시지 | send | |
| ws closed × durable(response·approval) | **queue → 재접속 시 재전송** | 🐛B1 수정 (2026-08-11, 사용자 승인): 이전엔 무음 드롭 |
| ws closed × ephemeral/heartbeat | skip(reason) | 스트림·하트비트는 큐잉 무의미 |
| untrusted × other → 승인 대기 × 무응답 10분 | **deny(approval-timeout)** | 🐛B2 수정: 이전엔 무한 대기 |
| 스크린샷 실패 전 사유 | skip(reason) + **응답에 사유 표기** | 🐛B3 수정: 이전엔 무설명 생략 |
| busy 중 신규 쿼리 | skip(busy-client-side-queue) + 안내 응답 | 🐛B4 **미수정**: "queued" 문구지만 실제 큐는 웹 클라이언트 몫 — Slack/직접 ws 클라이언트는 유실 가능. 후속 결정 필요 |

## Recon (규칙 C — 어떤 티어에서도 생략 불가)

log_stream: `~/.vibecheck/logs/effects-YYYY-MM-DD.jsonl` (choke: `effects/log.ts`,
`VIBECHECK_LOG_DIR`로 재지정 가능). 레코드: `{ts, effect, trigger_id, outcome,
reason?, detail?}`, outcome ∈ trigger|sent|queued|skipped|failed.

`scripts/recon-effects.mjs`가 **per-trigger left-join**으로 대사한다: 모든
trigger-id는 유예 15분 내 터미널 결과(sent|skipped|failed)를 가져야 하고,
queued는 pending(유예 내 정상)이다. 카운트는 distinct trigger-id 기준(멱등),
동일-윈도 카운트 등식·발송 시도 수 분모는 금지. 유예 경과 미대사만 위반이다.

에이전트 서버에 cron 등록 (health-check와 같은 방식):

```bash
(crontab -l 2>/dev/null; echo "0 * * * * node /path/to/VibeCheck/scripts/recon-effects.mjs >> /tmp/vibecheck-recon.log 2>&1") | crontab -
```

고빈도 스트림(`streaming_chunk`·`tool_status`·`ping`·`pong`)의 skip은 개별
로그에서 제외한다 — recon 등식의 트리거(query·schedule·approval·screenshot)에
영향 없음. 알람 채널은 미정 (서버 레포와 공통 미결 — 아래 참조).

## 게이트

- CI: [.github/workflows/governance.yml](./.github/workflows/governance.yml) — 스캐너 + 매트릭스 테스트 + 빌드
- pre-push: `git config core.hooksPath scripts/git-hooks` 로 설치 (1회)

## 알려진 한계 · 후속 작업 (정직하게)

- **[manual] 항목**: 스캐너 출력 참조 — claude-query(위임 효과), slack-notify,
  self-update, self-restart, local-state, ops-restart, 그리고 self-hosted 서버
  측 ws-uplink. 자동 대사가 없는 것들이며 숨기지 않는다.
- **self-hosted 미러 미적용**: B1~B3 수정과 effect 로그는 cloud/agent-ts에만
  구현됐다. `self-hosted/src/shared/{security,screenshot}.ts`는 수정 전 사본과
  동일 로직 (core.ts broadcast에도 B1류 무음 드롭 존재) — 후속: effects 모듈
  이식.
- **trigger_id 프로토콜 에코 없음**: 서버(VibeCheck-server)는 api_key당 pending
  trigger 1개로 쿼리↔응답을 근사한다. query에 trigger_id를 실어 response에
  에코하면 정확해지지만 **서버의 pending_triggers 로직과 동시 변경 필요 —
  단독 진행 금지** (2026-08-11 서버 세션 합의).
- 유예 15분·승인 타임아웃 10분·큐 상한 50은 추정 초깃값이다.

## 불변식 태그 요약 (playbook 원칙 5)

| 불변식 | 태그 |
|---|---|
| 새 메시지 타입은 uplink 등급 지정 강제 | `[compile]` UPLINK_CLASS Record |
| 새 차원 값은 매트릭스 행 강제 | `[test]` policy.test.ts 크로스 프로덕트 |
| 출구는 등록된 위치에서만 | `[static]` scan-effects.mjs |
| 모든 트리거는 유예 내 대사 | `[recon]` recon-effects.mjs |
| 위임 효과·Slack·업데이트·재시작 | `[manual]` — 스캐너가 매 실행마다 출력 |
