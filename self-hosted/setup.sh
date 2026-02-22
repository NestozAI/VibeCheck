#!/bin/bash

# =============================================================================
# VibeCheck - 설치 스크립트
# =============================================================================

set -e

echo ""
echo "=========================================="
echo "  VibeCheck 설치"
echo "=========================================="
echo ""

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 현재 디렉토리 확인
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
CONDA_ENV="vibecheck"

# =============================================================================
# Python 확인
# =============================================================================

echo -e "${BLUE}[1/5]${NC} Python 확인..."

PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &> /dev/null; then
        version=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 8 ]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo -e "${RED}Error: Python 3.8+ 이 필요합니다.${NC}"
    echo "Python을 설치해주세요: https://www.python.org/downloads/"
    exit 1
fi

echo -e "  ${GREEN}$($PYTHON_CMD --version) 발견${NC}"

# =============================================================================
# 가상환경 생성 (venv → conda → 시스템 pip 순서)
# =============================================================================

echo ""
echo -e "${BLUE}[2/5]${NC} 가상환경 설정..."

ENV_MODE=""  # "venv", "conda", or "system"
ACTIVATE_CMD=""

# --- 1) venv 시도 ---
if [ -d "$VENV_DIR" ]; then
    echo -e "  ${YELLOW}기존 venv 환경 발견, 재사용합니다.${NC}"
    source "$VENV_DIR/bin/activate"
    ENV_MODE="venv"
    ACTIVATE_CMD="source $VENV_DIR/bin/activate"
else
    if "$PYTHON_CMD" -m venv "$VENV_DIR" 2>/dev/null; then
        echo -e "  ${GREEN}venv 환경 생성 완료${NC}"
        source "$VENV_DIR/bin/activate"
        ENV_MODE="venv"
        ACTIVATE_CMD="source $VENV_DIR/bin/activate"
    else
        echo -e "  ${YELLOW}venv 사용 불가${NC}"

        # Ubuntu/Debian에서 python3-venv 누락 안내
        if command -v apt &> /dev/null; then
            echo -e "  ${YELLOW}힌트: sudo apt install python3-venv 로 설치 가능${NC}"
        fi

        # --- 2) conda 폴백 ---
        if command -v conda &> /dev/null; then
            echo -e "  ${BLUE}conda로 폴백 시도...${NC}"
            if conda env list 2>/dev/null | grep -q "^$CONDA_ENV "; then
                echo -e "  ${YELLOW}기존 conda 환경 발견, 재사용합니다.${NC}"
            else
                if conda create -n "$CONDA_ENV" python=3.11 -y 2>/dev/null; then
                    echo -e "  ${GREEN}conda 환경 생성 완료${NC}"
                else
                    echo -e "  ${YELLOW}conda 환경 생성 실패${NC}"
                fi
            fi

            # conda 활성화 시도
            if eval "$(conda shell.bash hook 2>/dev/null)" && conda activate "$CONDA_ENV" 2>/dev/null; then
                ENV_MODE="conda"
                ACTIVATE_CMD="conda activate $CONDA_ENV"
            else
                echo -e "  ${YELLOW}conda 활성화 실패${NC}"
            fi
        fi

        # --- 3) 시스템 pip 폴백 ---
        if [ -z "$ENV_MODE" ]; then
            echo -e "  ${YELLOW}⚠ 가상환경 없이 시스템 pip에 직접 설치합니다.${NC}"
            ENV_MODE="system"
            ACTIVATE_CMD=""
        fi
    fi
fi

echo -e "  ${GREEN}환경 모드: ${ENV_MODE}${NC}"

# =============================================================================
# 의존성 설치
# =============================================================================

echo ""
echo -e "${BLUE}[3/5]${NC} 의존성 설치..."

PIP_FLAGS="-q"
if [ "$ENV_MODE" = "system" ]; then
    PIP_FLAGS="$PIP_FLAGS --user"
fi

pip install --upgrade pip $PIP_FLAGS
pip install -r requirements.txt $PIP_FLAGS

echo -e "  ${GREEN}패키지 설치 완료${NC}"

# =============================================================================
# Playwright 브라우저 설치
# =============================================================================

echo ""
echo -e "${BLUE}[4/5]${NC} Playwright 브라우저 설치 (UI 스크린샷용)..."

playwright install chromium --with-deps 2>/dev/null || playwright install chromium 2>/dev/null || \
    echo -e "  ${YELLOW}Playwright 설치 건너뜀 (스크린샷 기능 사용 불가)${NC}"

echo -e "  ${GREEN}완료${NC}"

# =============================================================================
# 환경변수 설정
# =============================================================================

echo ""
echo -e "${BLUE}[5/5]${NC} Slack 연동 설정"
echo ""
echo "=========================================="
echo "  Slack App 토큰이 필요합니다."
echo "  https://api.slack.com/apps 에서 발급받으세요."
echo "=========================================="
echo ""

# Bot Token 입력
echo "Slack Bot Token (xoxb-로 시작)"
read -p "  Bot Token: " BOT_TOKEN
while [ -z "$BOT_TOKEN" ]; do
    echo "  필수 입력값입니다."
    read -p "  Bot Token: " BOT_TOKEN
done

echo ""

# App Token 입력
echo "Slack App Token (xapp-로 시작, Socket Mode용)"
read -p "  App Token: " APP_TOKEN
while [ -z "$APP_TOKEN" ]; do
    echo "  필수 입력값입니다."
    read -p "  App Token: " APP_TOKEN
done

echo ""

# 작업 디렉토리 입력
DEFAULT_DIR=$(pwd)
echo "작업할 디렉토리 경로"
read -p "  작업 디렉토리 [$DEFAULT_DIR]: " WORK_DIR
WORK_DIR=${WORK_DIR:-$DEFAULT_DIR}

# .env 파일 생성
cat > .env << EOF
# VibeCheck 환경설정
# 자동 생성됨

SLACK_BOT_TOKEN=$BOT_TOKEN
SLACK_APP_TOKEN=$APP_TOKEN
WORK_DIR=$WORK_DIR
EOF

echo ""
echo -e "${GREEN}.env 파일이 생성되었습니다.${NC}"

# =============================================================================
# 완료
# =============================================================================

echo ""
echo "=========================================="
echo -e "  ${GREEN}설치 완료!${NC}"
echo "=========================================="
echo ""
echo "실행 방법:"
echo ""
if [ -n "$ACTIVATE_CMD" ]; then
    echo -e "  ${YELLOW}${ACTIVATE_CMD}${NC}"
fi
echo -e "  ${YELLOW}python main.py${NC}"
echo ""
echo "또는 한 줄로:"
echo ""
echo -e "  ${YELLOW}./run.sh${NC}"
echo ""
