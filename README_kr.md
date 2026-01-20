# VibeCheck

> **어디서든 Claude Code를 원격 제어하세요.**

[![English](https://img.shields.io/badge/Language-English-blue)](./README.md)
[![Korean](https://img.shields.io/badge/Language-한국어-red)](./README_kr.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![PyPI](https://img.shields.io/pypi/v/vibecheck-agent?color=green)](https://pypi.org/project/vibecheck-agent/)

**VibeCheck**은 서버에서 실행 중인 Claude Code CLI를 웹 브라우저로 제어할 수 있게 해줍니다. 집, 카페, 이동 중 어디서든 코드를 작성하고 수정할 수 있습니다.

---

## 버전 선택

| **🛠️ 셀프 호스팅 (오픈소스)** | **☁️ 클라우드 버전** |
| :--- | :--- |
| ✅ **무료** - 자체 서버 사용 | ⚡ **서버 설정 불필요** - 설치만 하면 끝 |
| 💻 환경 완전 제어 | 🌐 웹 기반 채팅 인터페이스 |
| 🔧 직접 설치 및 유지보수 | 📦 `pip install vibecheck-agent` |
| [👇 **아래 설치 가이드 참조**](#셀프-호스팅-설정) | [👉 **시작하기**](https://vibecheck.nestoz.co) |

---

## 셀프 호스팅 설정

서버와 Slack 앱을 완전히 제어하고 싶은 사용자를 위한 옵션.

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

### Slack 앱 설정 (셀프 호스팅 전용)

<details>
<summary>Slack 앱 설정 가이드 펼치기</summary>

#### 1단계: Slack 앱 생성

1. [api.slack.com/apps](https://api.slack.com/apps) 접속
2. **"Create New App"** → **"From scratch"** 클릭
3. 앱 이름 입력 (예: "VibeCheck") 후 워크스페이스 선택

#### 2단계: Socket Mode 활성화

1. **Settings → Socket Mode** 이동
2. **Enable Socket Mode** → ON
3. **"Generate"** 클릭하여 App-Level Token 생성
   - Token Name: `vibecheck-socket`
   - Scope: `connections:write`
4. `xapp-...` 로 시작하는 토큰 복사 → `SLACK_APP_TOKEN`

#### 3단계: Bot Token Scopes 설정

**OAuth & Permissions → Bot Token Scopes** 에서 추가:

| Scope | 설명 |
|-------|------|
| `chat:write` | 봇으로 메시지 전송 |
| `files:write` | 이미지 및 파일 업로드 |
| `im:history` | DM 메시지 기록 읽기 |
| `im:read` | DM 채널 정보 접근 |
| `im:write` | DM 시작 |
| `users:read` | 사용자 정보 보기 |

#### 4단계: Events 활성화

1. **Event Subscriptions** 이동
2. **Enable Events** → ON
3. **Subscribe to bot events** 에서 추가:
   - `message.im` - DM 메시지 수신
   - `app_mention` - @멘션 응답
   - `app_home_opened` - 홈 탭 표시

#### 5단계: Interactivity 활성화

1. **Interactivity & Shortcuts** 이동
2. **Interactivity** → ON

#### 6단계: App Home 활성화

1. **App Home** 이동
2. **Home Tab** 과 **Messages Tab** 활성화
3. **"Allow users to send Slash commands and messages from the messages tab"** 체크

#### 7단계: 워크스페이스에 앱 설치

1. **OAuth & Permissions** 이동
2. **"Install to Workspace"** 클릭
3. **Bot User OAuth Token** (`xoxb-...`) 복사 → `SLACK_BOT_TOKEN`

#### 8단계: 환경 설정

`self-hosted/` 디렉토리에 `.env` 파일 생성:

```bash
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here
WORK_DIR=/path/to/your/project
```

</details>

---

## 클라우드 버전

VibeCheck을 사용하는 가장 쉬운 방법. 서버 설정이 필요 없습니다!

### 빠른 시작

#### 1. 로그인
[vibecheck.nestoz.co](https://vibecheck.nestoz.co) 방문 후 이메일로 로그인하세요.

#### 2. API Key 받기
대시보드에서 API 키를 복사하세요.

#### 3. Agent 설치 및 실행
```bash
pip install vibecheck-agent
vibecheck-agent --key YOUR_API_KEY --dir /path/to/your/project
```

끝! 이제 Chat 페이지를 열고 코딩을 시작하세요.

### Agent 옵션

```bash
vibecheck-agent --key YOUR_API_KEY --dir /path/to/project

옵션:
  --key    VibeCheck API 키 (vibe_sk_...)
  --dir    작업 디렉토리 (기본값: 현재 디렉토리)
  --server 커스텀 서버 URL (선택사항)
```

---

## 데모

![Architecture](./assets/architecture.png)

*시스템 아키텍처: 웹 브라우저 ↔ 클라우드 서버 ↔ 로컬 Agent ↔ Claude Code*

![UX Demo](./assets/ux_demo.png)

*UI 렌더링, 디자인 수정을 요청하고 즉각적인 시각적 피드백을 받으세요 - 모두 웹에서.*

---

## 주요 기능

- **자연어 코딩** - Claude Code와 대화하며 코드 작성, 수정, 실행
- **시각적 피드백** - UI 스크린샷과 시각화를 생성하고 웹 채팅에 표시
- **이미지 업로드** - 드래그 앤 드롭으로 채팅에 직접 이미지 업로드
- **보안 레이어** - 경로 기반 접근 제어 및 승인 시스템
- **세션 유지** - 대화가 메시지 간에 이어짐
- **스크린샷 생성** - HTML/프로젝트 미리보기 자동 스크린샷

---

## 보안 시스템

![Security Flow](./assets/security_flow.png)

VibeCheck은 파일 시스템을 보호하기 위한 경로 기반 보안 시스템을 포함합니다.

### 작동 방식

1. **신뢰 경로**: 기본적으로 작업 디렉토리만 신뢰됨
2. **경로 감지**: Claude가 신뢰되지 않은 디렉토리에 접근하려 하면 봇이 감지
3. **승인 UI**: Block Kit 메시지가 승인 옵션과 함께 표시:
   - **승인 및 실행** - 일회성 접근
   - **승인 (영구)** - 신뢰 목록에 경로 추가
   - **거절** - 요청 취소

### 안전한 시스템 명령어

다음 읽기 전용 명령어는 자동 승인됩니다:

```
nvidia-smi, df, free, uptime, whoami, hostname,
cat /proc/cpuinfo, cat /proc/meminfo, ps, top,
ls, pwd, date, which, echo
```

---

## 사용 예시

### UI 빌드

```
사용자: 이메일과 비밀번호 필드가 있는 로그인 폼 만들어줘, 모던한 다크 테마로

봇: index.html에 로그인 폼을 만들었습니다...
    [렌더링된 UI 스크린샷 업로드]
```

### 코드 수정

```
사용자: 이메일 형식 검사하는 폼 유효성 검사 추가해줘

봇: 이메일 유효성 검사를 추가했습니다...
    [업데이트된 스크린샷 업로드]
```

### 시스템 모니터링

```
사용자: GPU 상태 확인해줘

봇: nvidia-smi 출력:
    +------------------------------------------+
    | NVIDIA-SMI 525.85.12  CUDA Version: 12.0 |
    ...
```

---

## 요구사항

- Python 3.8+
- Claude Code CLI (`claude` 명령어)
- 웹 브라우저 (클라우드 버전) 또는 Slack 워크스페이스 (셀프 호스팅)

---

## 파일 구조

```
VibeCheck/
├── cloud/
│   └── agent/           # PyPI 패키지 소스 (vibecheck-agent)
│       ├── agent.py     # Agent 구현
│       └── html_screenshot.py
├── self-hosted/
│   ├── main.py          # 셀프 호스팅 봇
│   ├── setup.sh         # 설치 스크립트
│   └── run.sh           # 실행 스크립트
├── assets/
│   ├── architecture.png
│   ├── ux_demo.png
│   └── security_flow.png
└── README.md
```

---

## 문제 해결

### Agent가 연결되지 않음
- API 키가 올바른지 확인
- `claude` CLI가 설치되어 접근 가능한지 확인
- 인터넷 연결 확인

### 응답이 오지 않음
- (셀프 호스팅) **Event Subscriptions** → `message.im` 구독 확인
- (클라우드) Agent가 실행 중인지 확인하고 Chat 페이지 확인

### 스크린샷이 생성되지 않음
- playwright 설치: `pip install playwright && playwright install chromium`

---

## 라이선스

MIT

## 기여

기여를 환영합니다! 이슈를 열거나 풀 리퀘스트를 제출해주세요.

---

<p align="center">
  <a href="https://vibecheck.nestoz.co">
    <img src="https://img.shields.io/badge/VibeCheck_Cloud_시작하기-00ff00?style=for-the-badge" alt="VibeCheck Cloud 시작하기">
  </a>
</p>
