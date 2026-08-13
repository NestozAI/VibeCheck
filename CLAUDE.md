# VibeCheck

Claude Code를 서버에서 24/7 구동하는 agent(npm: `vibecheck-agent`,
`cloud/agent-ts/`)와 self-hosted 서버(`self-hosted/`). 클라우드 백엔드는 별도
레포(VibeCheck-server)다. 구조·정책·recon은 [GOVERNANCE.md](./GOVERNANCE.md) 참조.

## Effect Governance 규칙 (binding)

이 리포는 effects.manifest.json 기반 effect governance를 따른다. 코드를 수정할 때:

1. 네트워크/파일/프로세스/서드파티 SDK를 다루는 코드는 effects.manifest.json
   해당 효과의 allowed_sites 안에서만 작성한다. WebSocket 전송은
   `agent.ts#send`(정책 경유), 스크린샷은 `screenshot.ts#screenshotProject`,
   effect 로그는 `effects/log.ts`를 경유한다.
2. 새 출구(새 SDK, 새 API, 새 write 경로)를 추가할 때는 코드보다 먼저
   effects.manifest.json에 등록한다. choke_point·log_stream·recon 세 필드를
   채우지 못하면 아직 추가할 준비가 안 된 것 — 사용자에게 묻는다.
3. "실행하지 않는" 경로도 `logEffect({outcome: "skipped", reason})`으로
   기록한다. 조용히 흘러 지나가는 fall-through를 만들지 않는다.
4. 완료 선언 전에 `node scripts/scan-effects.mjs` 실행 — exit 0이 아니면
   완료가 아니다. UNREGISTERED는 임의로 exceptions에 넣지 말고 정식
   등록하거나 사용자에게 묻는다.
5. 스캐너를 통과시키려고 패턴 삭제·exceptions 확대 금지. 만료일 없는
   exception 금지.
6. 스캐너가 출력하는 [manual] recon 항목은 완료 보고에 그대로 전달한다.
7. 트리거→효과 경로에 새 분기 조건(필드 검사·상태·플래그)을 추가할 때는
   호출부 if로 두지 말고 `cloud/agent-ts/src/effects/policy.ts`의 입력
   차원으로 승격하고, policy.test.ts MATRIX에 새 조합 전체의 행을 추가한다.
   `cd cloud/agent-ts && npm test`가 깨지면 억누르지 말고 사용자에게 의도를
   묻는다. agent→서버 메시지 타입을 추가하면 UPLINK_CLASS가 컴파일 에러를
   낸다 — durable/ephemeral/heartbeat 등급을 정해서 통과시킨다.
8. recon은 per-trigger 대사(`scripts/recon-effects.mjs`)로만 구현한다:
   유예시간 내 sent|skipped|failed 대사, trigger-id dedupe, distinct
   trigger-id 카운트. 동일-윈도 카운트 등식(count==count)이나 발송 시도 수
   분모의 성공률로 구현하지 않는다.

## 크로스 레포 주의

- 프로토콜(`protocol.ts`)은 VibeCheck-server와 계약이다. 쿼리↔응답
  trigger_id 에코 확장은 서버의 pending_triggers 로직과 동시 변경 필요 —
  단독 진행 금지 (GOVERNANCE.md 후속 작업 참조).
- `self-hosted/src/shared/*`는 cloud/agent-ts/src의 사본 계열이다. agent-ts를
  고치면 미러 필요 여부를 확인하고, 못 하면 완료 보고에 명시한다.
