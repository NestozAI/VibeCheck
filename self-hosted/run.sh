#!/bin/bash

# Vibe Coding Bot 실행 스크립트

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# .env 확인
if [ ! -f ".env" ]; then
    echo "Error: .env 파일이 없습니다."
    echo "먼저 ./setup.sh 를 실행해주세요."
    exit 1
fi

# 가상환경 확인
if [ ! -d "venv" ]; then
    echo "Error: 가상환경이 없습니다."
    echo "먼저 ./setup.sh 를 실행해주세요."
    exit 1
fi

# 실행
source venv/bin/activate
echo "Vibe Coding Bot 시작..."
python main.py
