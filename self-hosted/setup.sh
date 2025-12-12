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

ENV_NAME="vibecheck"

# =============================================================================
# Conda 확인
# =============================================================================

echo -e "${BLUE}[1/4]${NC} Conda 확인..."

if ! command -v conda &> /dev/null; then
    echo -e "${RED}Error: Conda가 설치되어 있지 않습니다.${NC}"
    echo "Miniconda 또는 Anaconda를 설치해주세요."
    echo "https://docs.conda.io/en/latest/miniconda.html"
    exit 1
fi

echo -e "  ${GREEN}Conda 발견${NC}"

# =============================================================================
# Conda 환경 생성
# =============================================================================

echo ""
echo -e "${BLUE}[2/4]${NC} Conda 환경 생성 ($ENV_NAME)..."

if conda env list | grep -q "^$ENV_NAME "; then
    echo -e "  ${YELLOW}기존 환경 발견, 재사용합니다.${NC}"
else
    conda create -n $ENV_NAME python=3.11 -y
    echo -e "  ${GREEN}환경 생성 완료${NC}"
fi

# Conda 환경 활성화
eval "$(conda shell.bash hook)"
conda activate $ENV_NAME

# =============================================================================
# 의존성 설치
# =============================================================================

echo ""
echo -e "${BLUE}[3/4]${NC} 의존성 설치..."

pip install --upgrade pip -q
pip install -r requirements.txt -q

echo -e "  ${GREEN}패키지 설치 완료${NC}"

# =============================================================================
# 환경변수 설정 (bash로 직접 처리)
# =============================================================================

echo ""
echo -e "${BLUE}[4/4]${NC} Slack 연동 설정"
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
echo -e "  ${YELLOW}conda activate $ENV_NAME${NC}"
echo -e "  ${YELLOW}python main.py${NC}"
echo ""
echo "또는 한 줄로:"
echo ""
echo -e "  ${YELLOW}./run.sh${NC}"
echo ""
