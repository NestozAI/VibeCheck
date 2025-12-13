# VibeCheck

> Slack에서 직접 서버와 대화하세요.

[![English](https://img.shields.io/badge/Language-English-blue)](./README.md)
[![Korean](https://img.shields.io/badge/Language-한국어-red)](./README_kr.md)

**VibeCheck**은 Slack과 로컬 서버를 연결하는 브릿지입니다. 코드 실행, 시각화 생성, 파일 관리를 Slack 워크스페이스에서 보안 승인 시스템과 함께 사용할 수 있습니다.

![Architecture](./assets/architecture.png)

## 주요 기능

- **자연어 코딩** - AI와 대화하며 코드 작성, 수정, 실행
- **이미지 생성** - 차트와 시각화를 생성하고 Slack에 자동 업로드
- **보안 레이어** - 경로 기반 접근 제어 및 승인 시스템
- **안전한 시스템 명령어** - 읽기 전용 명령어 자동 승인 (nvidia-smi, df 등)
- **세션 유지** - 대화가 메시지 간에 이어짐

## 빠른 시작

```bash
git clone https://github.com/NestozAI/VibeCheck
cd VibeCheck/self-hosted
./setup.sh
./run.sh
```

## Slack 앱 설정

### 1단계: Slack 앱 생성

1. [api.slack.com/apps](https://api.slack.com/apps) 접속
2. **"Create New App"** → **"From scratch"** 클릭
3. 앱 이름 입력 (예: "VibeCheck") 후 워크스페이스 선택

### 2단계: Socket Mode 활성화

1. **Settings → Socket Mode** 이동
2. **Enable Socket Mode** → ON
3. **"Generate"** 클릭하여 App-Level Token 생성
   - Token Name: `vibecheck-socket`
   - Scope: `connections:write`
4. `xapp-...` 로 시작하는 토큰 복사 → `SLACK_APP_TOKEN`

### 3단계: Bot Token Scopes 설정

**OAuth & Permissions → Bot Token Scopes** 에서 추가:

| Scope | 설명 |
|-------|------|
| `chat:write` | 봇으로 메시지 전송 |
| `files:write` | 이미지 및 파일 업로드 |
| `im:history` | DM 메시지 기록 읽기 |
| `im:read` | DM 채널 정보 접근 |
| `im:write` | DM 시작 |
| `users:read` | 사용자 정보 보기 |

### 4단계: Events 활성화

1. **Event Subscriptions** 이동
2. **Enable Events** → ON
3. **Subscribe to bot events** 에서 추가:
   - `message.im` - DM 메시지 수신
   - `app_mention` - @멘션 응답
   - `app_home_opened` - 홈 탭 표시

### 5단계: Interactivity 활성화

1. **Interactivity & Shortcuts** 이동
2. **Interactivity** → ON

### 6단계: App Home 활성화

1. **App Home** 이동
2. **Home Tab** 과 **Messages Tab** 활성화
3. **"Allow users to send Slash commands and messages from the messages tab"** 체크

### 7단계: 워크스페이스에 앱 설치

1. **OAuth & Permissions** 이동
2. **"Install to Workspace"** 클릭
3. **Bot User OAuth Token** (`xoxb-...`) 복사 → `SLACK_BOT_TOKEN`

### 8단계: 환경 설정

`self-hosted/` 디렉토리에 `.env` 파일 생성:

```bash
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here
WORK_DIR=/path/to/your/project
```

## 보안 시스템

![Security Flow](./assets/security_flow.png)

VibeCheck은 파일 시스템을 보호하기 위한 경로 기반 보안 시스템을 포함합니다.

### 작동 방식

1. **신뢰 경로**: 기본적으로 `WORK_DIR`만 신뢰됨
2. **경로 감지**: 신뢰되지 않은 디렉토리의 경로를 언급하면 봇이 감지
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

### 봇 명령어

| 명령어 | 설명 |
|--------|------|
| `도움말` | 도움말 메시지 표시 |
| `리셋` | 새 대화 시작 |
| `/paths` | 신뢰 경로 목록 보기 |
| `/trust /경로` | 신뢰 목록에 경로 추가 |

## 사용 예시

### 기본 코딩

```
사용자: 현재 파일 구조 보여줘

봇: 📂 프로젝트 구조:
    ├── src/
    │   ├── index.ts
    │   └── utils.ts
    └── package.json
```

### 데이터 시각화

```
사용자: y=x², y=2x, y=3 을 한 그래프에 그려줘

봇: [그래프 이미지 업로드]
    📊 생성된 이미지: quadratic_comparison.png
```

### 시스템 모니터링

```
사용자: GPU 상태 확인해줘

봇: nvidia-smi 출력:
    +------------------------------------------+
    | NVIDIA-SMI 525.85.12  CUDA Version: 12.0 |
    ...
```

### 보안 승인

```
사용자: /var/log/myapp/ 의 로그 읽어줘

봇: ⚠️ 보안 경고
    AI가 다음 경로에 접근하려고 합니다:
    • /var/log/myapp/

    [✅ 승인 및 실행] [✅ 승인 (영구)] [❌ 거절]
```

## 요구사항

- Python 3.8+
- AI Coding CLI 도구
- Slack 워크스페이스

## 파일 구조

```
VibeCheck/
├── self-hosted/
│   ├── main.py          # 메인 봇 애플리케이션
│   ├── cleaner.py       # 출력 포맷팅
│   ├── setup.sh         # 설치 스크립트
│   ├── run.sh           # 실행 스크립트
│   └── .env             # 환경 변수
├── assets/
│   ├── architecture.png
│   └── security_flow.png
└── README.md
```

## 문제 해결

### 봇이 DM에 응답하지 않음
- **Event Subscriptions** → `message.im` 구독 확인
- **App Home** → Messages Tab 활성화 확인

### 이미지 업로드 실패
- `files:write` 스코프 추가 후 앱 재설치

### 경로 승인 버튼이 작동하지 않음
- Slack 앱 설정에서 **Interactivity** 활성화

## 라이선스

MIT

## 기여

기여를 환영합니다! 이슈를 열거나 풀 리퀘스트를 제출해주세요.
