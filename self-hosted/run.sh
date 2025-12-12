#!/bin/bash

# VibeCheck 실행 스크립트

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ENV_NAME="vibecheck"

# .env 확인
if [ ! -f ".env" ]; then
    echo "Error: .env 파일이 없습니다."
    echo "먼저 ./setup.sh 를 실행해주세요."
    exit 1
fi

# Conda 환경 활성화
eval "$(conda shell.bash hook)"
conda activate $ENV_NAME

echo "VibeCheck 시작..."
python main.py
