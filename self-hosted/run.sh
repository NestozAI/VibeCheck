#!/bin/bash

# VibeCheck 실행 스크립트

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# .env 확인
if [ ! -f ".env" ]; then
    echo "Error: .env 파일이 없습니다."
    echo "먼저 ./setup.sh 를 실행해주세요."
    exit 1
fi

# 가상환경 활성화 (venv → conda → 시스템 순서)
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif command -v conda &> /dev/null; then
    eval "$(conda shell.bash hook 2>/dev/null)" && conda activate vibecheck 2>/dev/null || true
fi

echo "VibeCheck 시작..."
python main.py
