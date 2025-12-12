#!/bin/bash

# =============================================================================
# Vibe Coding Bot - 설치 스크립트
# =============================================================================

set -e

echo ""
echo "=========================================="
echo "  Vibe Coding Bot 설치"
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

echo -e "${BLUE}[1/4]${NC} Python 버전 확인..."

# Python 확인
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo -e "${RED}Error: Python이 설치되어 있지 않습니다.${NC}"
    echo "Python 3.8 이상을 설치해주세요."
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2)
echo -e "  Python $PYTHON_VERSION 발견"

# =============================================================================
# 가상환경 생성
# =============================================================================

echo ""
echo -e "${BLUE}[2/4]${NC} 가상환경 생성..."

if [ -d "venv" ]; then
    echo -e "  ${YELLOW}기존 venv 발견, 재사용합니다.${NC}"
else
    $PYTHON_CMD -m venv venv
    echo -e "  ${GREEN}venv 생성 완료${NC}"
fi

# 가상환경 활성화
source venv/bin/activate

# =============================================================================
# 의존성 설치
# =============================================================================

echo ""
echo -e "${BLUE}[3/4]${NC} 의존성 설치..."

pip install --upgrade pip -q
pip install -r requirements.txt -q

echo -e "  ${GREEN}패키지 설치 완료${NC}"

# =============================================================================
# 환경변수 설정
# =============================================================================

echo ""
echo -e "${BLUE}[4/4]${NC} Slack 연동 설정"
echo ""
echo "=========================================="
echo "  Slack App 토큰이 필요합니다."
echo "  https://api.slack.com/apps 에서 발급받으세요."
echo "=========================================="
echo ""

# Python으로 대화형 설정
$PYTHON_CMD << 'PYTHON_SCRIPT'
import os

def get_input(prompt, required=True, default=""):
    while True:
        if default:
            value = input(f"{prompt} [{default}]: ").strip()
            if not value:
                value = default
        else:
            value = input(f"{prompt}: ").strip()

        if value or not required:
            return value
        print("  필수 입력값입니다. 다시 입력해주세요.")

print("Slack Bot Token (xoxb-로 시작)")
bot_token = get_input("  Bot Token")

print("")
print("Slack App Token (xapp-로 시작, Socket Mode용)")
app_token = get_input("  App Token")

print("")
print("Claude가 작업할 디렉토리 경로")
default_dir = os.getcwd()
work_dir = get_input("  작업 디렉토리", default=default_dir)

# .env 파일 생성
env_content = f"""# Vibe Coding Bot 환경설정
# 자동 생성됨

SLACK_BOT_TOKEN={bot_token}
SLACK_APP_TOKEN={app_token}
WORK_DIR={work_dir}
"""

with open(".env", "w") as f:
    f.write(env_content)

print("")
print("\033[0;32m.env 파일이 생성되었습니다.\033[0m")
PYTHON_SCRIPT

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
echo -e "  ${YELLOW}source venv/bin/activate${NC}"
echo -e "  ${YELLOW}python main.py${NC}"
echo ""
echo "또는 한 줄로:"
echo ""
echo -e "  ${YELLOW}./run.sh${NC}"
echo ""
