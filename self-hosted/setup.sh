#!/bin/bash

# =============================================================================
# VibeCheck - Setup Script
# =============================================================================

set -e

echo ""
echo "=========================================="
echo "  VibeCheck Setup"
echo "=========================================="
echo ""

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check current directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
CONDA_ENV="vibecheck"

# =============================================================================
# Check Python
# =============================================================================

echo -e "${BLUE}[1/5]${NC} Checking Python..."

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
    echo -e "${RED}Error: Python 3.8+ is required.${NC}"
    echo "Please install Python: https://www.python.org/downloads/"
    exit 1
fi

echo -e "  ${GREEN}$($PYTHON_CMD --version) found${NC}"

# =============================================================================
# Create virtual environment (venv -> conda -> system pip order)
# =============================================================================

echo ""
echo -e "${BLUE}[2/5]${NC} Setting up virtual environment..."

ENV_MODE=""  # "venv", "conda", or "system"
ACTIVATE_CMD=""

# --- 1) Try venv ---
if [ -d "$VENV_DIR" ]; then
    echo -e "  ${YELLOW}Existing venv environment found, reusing.${NC}"
    source "$VENV_DIR/bin/activate"
    ENV_MODE="venv"
    ACTIVATE_CMD="source $VENV_DIR/bin/activate"
else
    if "$PYTHON_CMD" -m venv "$VENV_DIR" 2>/dev/null; then
        echo -e "  ${GREEN}venv environment created${NC}"
        source "$VENV_DIR/bin/activate"
        ENV_MODE="venv"
        ACTIVATE_CMD="source $VENV_DIR/bin/activate"
    else
        echo -e "  ${YELLOW}venv unavailable${NC}"

        # Hint for missing python3-venv on Ubuntu/Debian
        if command -v apt &> /dev/null; then
            echo -e "  ${YELLOW}Hint: install with sudo apt install python3-venv${NC}"
        fi

        # --- 2) conda fallback ---
        if command -v conda &> /dev/null; then
            echo -e "  ${BLUE}Falling back to conda...${NC}"
            if conda env list 2>/dev/null | grep -q "^$CONDA_ENV "; then
                echo -e "  ${YELLOW}Existing conda environment found, reusing.${NC}"
            else
                if conda create -n "$CONDA_ENV" python=3.11 -y 2>/dev/null; then
                    echo -e "  ${GREEN}conda environment created${NC}"
                else
                    echo -e "  ${YELLOW}conda environment creation failed${NC}"
                fi
            fi

            # Try activating conda
            if eval "$(conda shell.bash hook 2>/dev/null)" && conda activate "$CONDA_ENV" 2>/dev/null; then
                ENV_MODE="conda"
                ACTIVATE_CMD="conda activate $CONDA_ENV"
            else
                echo -e "  ${YELLOW}conda activation failed${NC}"
            fi
        fi

        # --- 3) System pip fallback ---
        if [ -z "$ENV_MODE" ]; then
            echo -e "  ${YELLOW}⚠ Installing directly to system pip without virtual environment.${NC}"
            ENV_MODE="system"
            ACTIVATE_CMD=""
        fi
    fi
fi

echo -e "  ${GREEN}Environment mode: ${ENV_MODE}${NC}"

# =============================================================================
# Install dependencies
# =============================================================================

echo ""
echo -e "${BLUE}[3/5]${NC} Installing dependencies..."

PIP_FLAGS="-q"
if [ "$ENV_MODE" = "system" ]; then
    PIP_FLAGS="$PIP_FLAGS --user"
fi

pip install --upgrade pip $PIP_FLAGS
pip install -r requirements.txt $PIP_FLAGS

echo -e "  ${GREEN}Package installation complete${NC}"

# =============================================================================
# Install Playwright browser
# =============================================================================

echo ""
echo -e "${BLUE}[4/5]${NC} Installing Playwright browser (for UI screenshots)..."

playwright install chromium --with-deps 2>/dev/null || playwright install chromium 2>/dev/null || \
    echo -e "  ${YELLOW}Playwright installation skipped (screenshot feature unavailable)${NC}"

echo -e "  ${GREEN}Done${NC}"

# =============================================================================
# Configure environment variables
# =============================================================================

echo ""
echo -e "${BLUE}[5/5]${NC} Configuration"
echo ""

# Working directory input (required)
DEFAULT_DIR=$(pwd)
echo "Working directory path"
read -p "  Working directory [$DEFAULT_DIR]: " WORK_DIR
WORK_DIR=${WORK_DIR:-$DEFAULT_DIR}

echo ""

# Web port
read -p "  Web UI port [8501]: " WEB_PORT
WEB_PORT=${WEB_PORT:-8501}

echo ""

# Slack integration (optional)
echo "=========================================="
echo "  Slack integration (optional)"
echo "  Press Enter to skip if not using Slack."
echo "  Get tokens at https://api.slack.com/apps"
echo "=========================================="
echo ""

read -p "  Slack Bot Token (xoxb-...): " BOT_TOKEN
read -p "  Slack App Token (xapp-...): " APP_TOKEN

# Generate .env file
cat > .env << EOF
# VibeCheck configuration

WORK_DIR=$WORK_DIR
WEB_PORT=$WEB_PORT
EOF

if [ -n "$BOT_TOKEN" ] && [ -n "$APP_TOKEN" ]; then
    cat >> .env << EOF
SLACK_BOT_TOKEN=$BOT_TOKEN
SLACK_APP_TOKEN=$APP_TOKEN
EOF
    echo ""
    echo -e "  ${GREEN}Slack integration: enabled${NC}"
else
    echo ""
    echo -e "  ${YELLOW}Slack integration: disabled (web-only mode)${NC}"
fi

echo ""
echo -e "${GREEN}.env file has been created.${NC}"

# =============================================================================
# Complete
# =============================================================================

echo ""
echo "=========================================="
echo -e "  ${GREEN}Setup complete!${NC}"
echo "=========================================="
echo ""
echo "How to run:"
echo ""
if [ -n "$ACTIVATE_CMD" ]; then
    echo -e "  ${YELLOW}${ACTIVATE_CMD}${NC}"
fi
echo -e "  ${YELLOW}python main.py${NC}"
echo ""
echo "Then open in your browser:"
echo ""
echo -e "  ${YELLOW}http://localhost:${WEB_PORT}${NC}"
echo ""
echo "Or in one line:"
echo ""
echo -e "  ${YELLOW}./run.sh${NC}"
echo ""
