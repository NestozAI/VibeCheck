# Vibe Coding Bot

Slack에서 서버의 Claude Code를 원격 제어하세요.

```
[Slack] <---> [Your Server] <---> [Claude Code]
   DM으로 대화      Agent 실행       코드 수정
```

## 설치 방법

### Option 1: Cloud (쉬움) - 준비 중

```bash
# 1. vibe.dev에서 Slack 연동 (버튼 클릭)
# 2. Agent 실행
npx @vibe/agent
```

### Option 2: Self-Hosted (무료)

```bash
git clone https://github.com/sotaaz/vibe-coding-bot
cd vibe-coding-bot/self-hosted
./setup.sh
./run.sh
```

[→ Self-Hosted 상세 가이드](docs/self-hosted.md)

## 비교

| 기능 | Self-Hosted | Cloud |
|------|-------------|-------|
| 가격 | 무료 | $10/월~ |
| 설치 시간 | 10분 | 1분 |
| Slack App | 직접 생성 | 자동 연동 |
| 멀티 프로젝트 | 수동 설정 | 대시보드 |
| 지원 | GitHub Issues | 우선 지원 |

## 사용 예시

Slack DM:
```
나: 현재 파일 구조 보여줘
봇: 📂 프로젝트 구조입니다:
    ├── src/
    │   ├── index.ts
    │   └── utils.ts
    └── package.json

나: index.ts에 로깅 추가해줘
봇: ✅ 로깅 추가 완료!
    [변경 내용 표시]
```

## 요구사항

- Python 3.8+
- Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)
- Slack Workspace (App 생성 권한)

## License

MIT
