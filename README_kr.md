# VibeCheck

> **어디서든 Claude Code를 원격 제어하세요.**

[![English](https://img.shields.io/badge/Language-English-blue)](./README.md)
[![Korean](https://img.shields.io/badge/Language-한국어-red)](./README_kr.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![TypeScript](https://img.shields.io/badge/TypeScript-Agent-blue.svg)](./cloud/agent-ts/)
[![PyPI](https://img.shields.io/pypi/v/vibecheck-agent?color=green)](https://pypi.org/project/vibecheck-agent/)

**VibeCheck**는 서버에서 실행 중인 Claude Code CLI를 웹 브라우저로 제어할 수 있게 합니다. 집, 카페, 어디서든 코드를 작성하고 수정하세요.

---

## 버전 선택

| **🛠️ 셀프 호스팅 (오픈소스)** | **☁️ 클라우드 버전** |
| :--- | :--- |
| ✅ **무료** - 본인 서버 사용 | ⚡ **서버 설정 불필요** - 설치 즉시 사용 |
| 💻 환경 완전 제어 | 🌐 웹 기반 채팅 인터페이스 |
| 🔧 직접 설치 & 관리 | 📦 `pip install vibecheck-agent` |
| [👇 **설치 가이드 보기**](#셀프-호스팅-설정) | [👉 **시작하기**](https://vibecheck.nestoz.co) |

---

## 기능

- **자연어 코딩** — 채팅으로 Claude에게 코드 작성·수정·실행 지시
- **실시간 스트리밍** — Claude가 응답을 생성하는 동안 토큰 단위로 실시간 확인
- **도구 시각화** — Claude가 현재 어떤 도구를 사용하는지 실시간 표시 ("파일 읽는 중…", "명령 실행 중…")
- **스킬 시스템** — Claude의 동작과 도구 권한을 바꾸는 에이전트 프리셋 선택
- **태스크 스케줄러** — cron 표현식으로 반복 작업 자동화 (매일 git pull, 주간 의존성 감사 등)
- **시각적 피드백** — HTML/프로젝트 미리보기 스크린샷 자동 생성 후 채팅에 전송
- **이미지 업로드** — 채팅 창에 이미지 드래그 앤 드롭 지원
- **보안 레이어** — 경로 기반 접근 제어, 일회성/영구 승인 시스템
- **세션 연속성** — 메시지와 재연결 사이에도 대화 내용 유지
- **비용 추적** — 모든 응답에 USD 비용 및 토큰 사용량 상세 포함
- **모델 선택** — 쿼리별로 Claude 모델 지정 가능
- **커스텀 시스템 프롬프트** — 개별 쿼리에 시스템 프롬프트 직접 주입
- **커스텀 서브에이전트** — Task 도구를 통한 멀티에이전트 워크플로우 정의

---

## 클라우드 버전

가장 간편한 사용 방법입니다. 서버 설정이 필요 없어요!

### 빠른 시작

#### 1. 로그인
[vibecheck.nestoz.co](https://vibecheck.nestoz.co)에서 이메일로 로그인합니다.

#### 2. 에이전트 설치 & 실행
대시보드에서 원클릭 curl 명령어를 복사해 서버에서 실행하세요:
```bash
curl -sL https://vibecheck.nestoz.co/install/YOUR_API_KEY | bash
```

끝입니다! Chat 페이지를 열고 코딩을 시작하세요.

### 에이전트 옵션

```bash
vibecheck-agent --key YOUR_API_KEY --dir /path/to/project

옵션:
  --key    VibeCheck API 키 (vibe_sk_...)
  --dir    작업 디렉토리 (기본값: 현재 디렉토리)
  --server 커스텀 서버 URL (선택 사항)
```

> **TypeScript 에이전트** (`cloud/agent-ts/`)가 현재 활발히 관리되는 구현체입니다. Python 에이전트(`vibecheck-agent` on PyPI)는 레거시 버전입니다.

---

## 스킬 시스템

스킬은 에이전트 프리셋으로, 작업 유형에 따라 Claude의 시스템 프롬프트와 도구 권한을 설정합니다.

| 스킬 | 허용 도구 | 용도 |
|------|----------|------|
| 🔭 리서치 에이전트 | Read, Grep, Glob, WebSearch, WebFetch | 코드베이스 분석, 정보 수집 |
| 💻 코딩 에이전트 | 전체 | 코드 작성 및 수정 |
| 🔍 코드 리뷰 | Read, Grep, Glob | 버그·보안·품질 검토 |
| 🧪 테스트 실행 | Read, Glob, Bash | 테스트 실행 및 요약 |
| 📦 의존성 감사 | Read, Glob, Bash | 취약점·업데이트 확인 |
| 📋 Git 요약 | Read, Bash | 커밋 히스토리 요약 |
| 📝 문서 작성 | Read, Write, Glob | README 및 인라인 문서 |

웹 UI에서 `skill_id`를 쿼리와 함께 전송하면, 에이전트가 해당 프리셋을 적용해 Claude를 실행합니다.

---

## 태스크 스케줄러

cron 스케줄로 작업을 자동화하세요:

```jsonc
// 서버 → 에이전트
{ "type": "schedule_add", "cron": "0 9 * * 1-5", "message": "테스트 실행 후 실패 보고해줘", "skill_id": "test-runner" }

// 에이전트가 평일 오전 9시마다 자동 실행 후 결과를 웹 UI로 전송
```

스케줄은 `~/.vibecheck/schedules.json`에 저장되어 에이전트 재시작 후에도 유지됩니다.  
사용자 쿼리 진행 중에 스케줄이 발생하면 큐에 저장되었다가 쿼리 완료 후 자동으로 실행됩니다.

---

## WebSocket 프로토콜

TypeScript 에이전트는 WebSocket으로 서버와 통신합니다. 모든 메시지는 JSON 형식입니다.

### 에이전트 → 서버

| 메시지 | 설명 |
|--------|------|
| `response` | 최종 응답 — `result`, `cost_usd`, `num_turns`, `usage`(토큰 상세), 선택적 `images` 포함 |
| `streaming_chunk` | 실시간 텍스트 델타 (`delta`, `index`) — Claude 생성 중 지속 전송 |
| `tool_status` | 도구 시작/종료 이벤트 (`tool`, `status`, `label`, 선택적 `detail`) |
| `approval_required` | 작업 범위 밖 경로 접근에 대한 사용자 승인 요청 |
| `session_sync` | 연결 시 현재 `work_dir`와 `session_id` 보고 |
| `session_update` | 세션 ID 변경 시 서버에 알림 |
| `skill_list_response` | 사용 가능한 스킬 목록 반환 |
| `schedule_list_response` | 등록된 스케줄 태스크 목록 반환 |
| `schedule_add_response` | 태스크 추가 결과 |
| `ping` / `pong` | 연결 유지 |

### 서버 → 에이전트

| 메시지 | 설명 |
|--------|------|
| `query` | 쿼리 실행 — `model`, `skill_id`, `system_prompt`, `agents` 지원 |
| `approval` | 승인 요청에 대한 사용자 응답 |
| `interrupt` | 현재 쿼리 중단 |
| `add_trusted_path` | 파일 경로를 영구 신뢰 목록에 추가 |
| `skill_list` | 스킬 목록 요청 |
| `schedule_add` | 새 스케줄 태스크 추가 |
| `schedule_remove` | ID로 태스크 삭제 |
| `schedule_toggle` | 태스크 활성화/비활성화 |
| `schedule_list` | 스케줄 태스크 목록 요청 |
| `session_info` | 서버에서 세션 ID 동기화 |
| `ping` / `pong` | 연결 유지 |

### `query` 메시지 필드

```jsonc
{
  "type": "query",
  "message": "인증 모듈 리팩토링해줘",
  "model": "claude-opus-4-5",          // 선택 — 모델 지정
  "skill_id": "coding",                // 선택 — 스킬 프리셋
  "system_prompt": "항상 한국어로 답변해줘", // 선택 — 쿼리별 시스템 프롬프트
  "agents": {                          // 선택 — 커스텀 서브에이전트
    "reviewer": {
      "description": "코드 품질 검토 에이전트",
      "prompt": "보안과 정확성을 중심으로 검토해줘",
      "tools": ["Read", "Grep"]
    }
  }
}
```

---

## 보안 시스템

VibeCheck는 파일 시스템을 보호하기 위한 경로 기반 보안 시스템을 포함합니다.

### 동작 방식

1. **신뢰 경로** — 기본적으로 작업 디렉토리만 신뢰됨
2. **경로 감지** — Claude가 신뢰 범위 밖의 경로에 접근하려 할 때 에이전트가 이를 차단
3. **승인 UI** — 웹 UI에 승인 요청 표시:
   - **승인** — 이번 한 번만 허용
   - **영구 승인** — 신뢰 경로 목록에 추가
   - **거부** — 작업 취소

### 자동 승인 명령어

다음 읽기 전용 시스템 명령은 항상 자동 허용됩니다:

```
nvidia-smi, df, free, uptime, whoami, hostname,
cat /proc/cpuinfo, cat /proc/meminfo, ps, top,
ls, pwd, date, which, echo
```

---

## 셀프 호스팅 설정

서버와 Slack 앱을 직접 관리하고 싶은 사용자를 위한 설정입니다.

### 빠른 시작

#### Linux / macOS

```bash
git clone https://github.com/NestozAI/VibeCheck
cd VibeCheck/self-hosted
./setup.sh
./run.sh
```

#### Windows

```cmd
git clone https://github.com/NestozAI/VibeCheck
cd VibeCheck\self-hosted
setup.bat
run.bat
```

<details>
<summary>Slack 앱 설정 가이드 펼치기</summary>

#### 1단계: Slack 앱 생성

1. [api.slack.com/apps](https://api.slack.com/apps) 접속
2. **"Create New App"** → **"From scratch"**
3. 앱 이름(예: "VibeCheck") 입력 후 워크스페이스 선택

#### 2단계: Socket Mode 활성화

1. **Settings → Socket Mode** 이동
2. **Enable Socket Mode** 켜기
3. **"Generate"** 클릭 → App-Level Token 생성
   - 이름: `vibecheck-socket`, Scope: `connections:write`
4. `xapp-...`로 시작하는 토큰 복사 → `SLACK_APP_TOKEN`

#### 3단계: Bot Token Scopes 설정

**OAuth & Permissions → Bot Token Scopes**에 다음 추가:

| Scope | 설명 |
|-------|------|
| `chat:write` | 봇으로 메시지 전송 |
| `files:write` | 이미지 및 파일 업로드 |
| `im:history` | DM 히스토리 읽기 |
| `im:read` | DM 채널 정보 접근 |
| `im:write` | 다이렉트 메시지 시작 |
| `users:read` | 사용자 정보 조회 |

#### 4단계: 이벤트 활성화

1. **Event Subscriptions** 이동
2. **Enable Events** 켜기
3. **Subscribe to bot events** 추가: `message.im`, `app_mention`, `app_home_opened`

#### 5~7단계: Interactivity, App Home, 설치

1. **Interactivity & Shortcuts** → Interactivity 활성화
2. **App Home** → Home Tab, Messages Tab 활성화
3. **OAuth & Permissions** → Install to Workspace → `xoxb-...` 토큰 복사

#### 8단계: 환경 변수 설정

`self-hosted/.env` 파일 생성:

```bash
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here
WORK_DIR=/path/to/your/project
```

</details>

---

## 파일 구조

```
VibeCheck/
├── cloud/
│   ├── agent-ts/            # TypeScript 에이전트 (현재 활발히 관리)
│   │   └── src/
│   │       ├── agent.ts     # 메인 WebSocket 에이전트, 스킬·스케줄러 통합
│   │       ├── claude.ts    # Claude Agent SDK 래퍼 (스트리밍, 도구, 세션)
│   │       ├── protocol.ts  # WebSocket 메시지 타입 정의
│   │       ├── skills.ts    # 내장 스킬 프리셋
│   │       ├── scheduler.ts # cron 기반 태스크 스케줄러
│   │       └── security.ts  # 경로 기반 접근 제어
│   └── agent/               # Python 에이전트 (레거시, PyPI)
├── self-hosted/
│   ├── main.py              # 셀프 호스팅 Slack 봇
│   ├── setup.sh
│   └── run.sh
├── assets/
│   ├── architecture.png
│   ├── ux_demo.png
│   └── security_flow.png
└── README.md
```

---

## 요구 사항

- Node.js 18+ (TypeScript 에이전트) 또는 Python 3.8+ (레거시 에이전트)
- Claude Code CLI (`claude` 명령어가 PATH에 있어야 함)
- 웹 브라우저 (클라우드 버전) 또는 Slack 워크스페이스 (셀프 호스팅)

---

## 문제 해결

### 에이전트가 연결되지 않는 경우
- API 키가 올바른지 확인
- `claude` CLI가 설치되어 PATH에 있는지 확인
- 인터넷 연결 및 방화벽 규칙 확인

### 응답이 오지 않는 경우
- (클라우드) 에이전트 프로세스가 실행 중인지 확인
- (셀프 호스팅) **Event Subscriptions** → `message.im` 구독 여부 확인

### 스크린샷이 생성되지 않는 경우
- TypeScript 에이전트: `npx playwright install chromium`
- Python 에이전트: `pip install playwright && playwright install chromium`

---

## 라이선스

MIT

## 기여

이슈나 풀 리퀘스트를 통한 기여를 환영합니다!

---

<p align="center">
  <a href="https://vibecheck.nestoz.co">
    <img src="https://img.shields.io/badge/VibeCheck_Cloud_시작하기-00ff00?style=for-the-badge" alt="Try VibeCheck Cloud">
  </a>
</p>
