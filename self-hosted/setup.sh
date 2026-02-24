#!/bin/bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     VibeCheck Self-Hosted Setup      ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
echo ""

# ------------------------------------------------------------------
# 1. Check Node.js
# ------------------------------------------------------------------
echo -e "${YELLOW}[1/4] Checking Node.js...${NC}"

if ! command -v node &> /dev/null; then
  echo -e "${RED}Node.js is not installed.${NC}"
  echo "Install Node.js 18+ from https://nodejs.org/ or via nvm:"
  echo "  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash"
  echo "  nvm install 20"
  exit 1
fi

NODE_VERSION=$(node -v | sed 's/v//' | cut -d. -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
  echo -e "${RED}Node.js 18+ required. Current: $(node -v)${NC}"
  echo "Update via nvm: nvm install 20 && nvm use 20"
  exit 1
fi

echo -e "${GREEN}  Node.js $(node -v) ✓${NC}"

# ------------------------------------------------------------------
# 2. Install dependencies
# ------------------------------------------------------------------
echo -e "${YELLOW}[2/4] Installing dependencies...${NC}"

npm install

echo -e "${GREEN}  Dependencies installed ✓${NC}"

# ------------------------------------------------------------------
# 3. Configure .env
# ------------------------------------------------------------------
echo -e "${YELLOW}[3/4] Configuring environment...${NC}"

if [ -f .env ]; then
  echo -e "  .env already exists. Skipping."
else
  cp .env.example .env
  echo ""

  # Working directory
  read -p "  Working directory (default: current dir): " WORK_DIR
  if [ -n "$WORK_DIR" ]; then
    sed -i "s|WORK_DIR=.|WORK_DIR=$WORK_DIR|" .env
  fi

  # Port
  read -p "  Web port (default: 8501): " PORT
  if [ -n "$PORT" ]; then
    sed -i "s|WEB_PORT=8501|WEB_PORT=$PORT|" .env
  fi

  # Language
  read -p "  Language (en/ko, default: en): " LANG
  if [ -n "$LANG" ]; then
    sed -i "s|BOT_LANG=en|BOT_LANG=$LANG|" .env
  fi

  # Slack
  echo ""
  read -p "  Enable Slack integration? (y/N): " SLACK
  if [[ "$SLACK" =~ ^[Yy]$ ]]; then
    read -p "  Slack Bot Token (xoxb-...): " BOT_TOKEN
    read -p "  Slack App Token (xapp-...): " APP_TOKEN
    sed -i "s|SLACK_BOT_TOKEN=|SLACK_BOT_TOKEN=$BOT_TOKEN|" .env
    sed -i "s|SLACK_APP_TOKEN=|SLACK_APP_TOKEN=$APP_TOKEN|" .env
  fi

  echo -e "${GREEN}  .env configured ✓${NC}"
fi

# ------------------------------------------------------------------
# 4. Build
# ------------------------------------------------------------------
echo -e "${YELLOW}[4/4] Building...${NC}"

npm run build

echo -e "${GREEN}  Build complete ✓${NC}"

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         Setup Complete!               ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""
echo "  Start:  npm start"
echo "  Dev:    npm run dev"
echo ""

PORT=${PORT:-8501}
echo -e "  Web UI: ${BLUE}http://localhost:${PORT}${NC}"
echo ""
