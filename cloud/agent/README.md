# VibeCheck Agent

Slack에서 Claude Code를 원격 제어하는 Agent입니다.

## 설치

```bash
pip install vibecheck-agent
```

## 사용법

```bash
vibecheck-agent --key=YOUR_API_KEY
```

API Key는 https://vibecheck.nestoz.co 에서 Slack 로그인 후 대시보드에서 확인할 수 있습니다.

## 옵션

- `--key`, `-k`: API Key (필수)
- `--dir`, `-d`: 작업 디렉토리 (기본: 현재 디렉토리)
- `--server`, `-s`: 서버 URL (기본: wss://vibecheck.nestoz.co/ws/agent)

## 링크

- 홈페이지: https://vibecheck.nestoz.co
- GitHub: https://github.com/NestozAI/VibeCheck
