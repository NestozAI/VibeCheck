# Self-Hosted 설치 가이드

직접 서버에 설치해서 무료로 사용하는 방법입니다.

## 1. 사전 준비

### Claude Code CLI 설치
```bash
npm install -g @anthropic-ai/claude-code
claude --version
```

### Slack App 생성

1. [api.slack.com/apps](https://api.slack.com/apps) 접속
2. **Create New App** → **From scratch**
3. App 이름 입력 (예: Vibe Coding Bot)
4. Workspace 선택

### Slack App 설정

**OAuth & Permissions > Bot Token Scopes:**
- `chat:write`
- `im:history`
- `im:read`
- `im:write`
- `app_mentions:read`

**Socket Mode:**
- Enable Socket Mode: **On**
- App Token 생성 (connections:write)

**Event Subscriptions:**
- Enable Events: **On**
- Subscribe to bot events:
  - `app_mention`
  - `message.im`

**App Home:**
- Messages Tab: **On**

### 앱 설치
**Install App** → **Install to Workspace**

## 2. 설치

```bash
git clone https://github.com/sotaaz/vibe-coding-bot
cd vibe-coding-bot/self-hosted
./setup.sh
```

설치 스크립트가 물어보는 정보:
- **Bot Token**: `xoxb-` 로 시작 (OAuth & Permissions에서 복사)
- **App Token**: `xapp-` 로 시작 (Basic Information > App Token에서 복사)
- **작업 디렉토리**: Claude가 작업할 경로

## 3. 실행

```bash
./run.sh
```

## 4. 사용

Slack에서:
- 봇에게 DM 보내기
- 또는 채널에서 `@봇이름 메시지` 멘션

### 명령어

| 명령 | 설명 |
|------|------|
| `리셋` | 새 대화 시작 |
| `도움말` | 도움말 보기 |

## 문제 해결

### "Claude가 응답하지 않습니다"
- Claude CLI 설치 확인: `claude --version`
- 작업 디렉토리 권한 확인

### "Slack 연결 실패"
- Bot Token, App Token 확인
- Socket Mode 활성화 확인
- Event Subscriptions 설정 확인

### 로그 확인
```bash
# 실행 시 로그 출력됨
./run.sh
```
