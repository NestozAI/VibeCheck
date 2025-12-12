#!/bin/bash

# VibeCheck Agent 실행 스크립트

# 인자 확인
if [ -z "$1" ]; then
    echo "Usage: ./run.sh <API_KEY> [WORK_DIR]"
    echo ""
    echo "Examples:"
    echo "  ./run.sh vibe_sk_abc123"
    echo "  ./run.sh vibe_sk_abc123 /path/to/project"
    exit 1
fi

API_KEY=$1
WORK_DIR=${2:-$(pwd)}

python agent.py --key="$API_KEY" --dir="$WORK_DIR"
