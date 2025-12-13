# VibeCheck

> **Talk to your server directly from Slack.**

[![English](https://img.shields.io/badge/Language-English-blue)](./README.md)
[![Korean](https://img.shields.io/badge/Language-한국어-red)](./README_kr.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![Waitlist](https://img.shields.io/badge/Cloud_Version-Join_Waitlist-39FF14?style=flat&logo=google-forms&logoColor=black)](https://NestozAI.github.io/VibeCheck)

**VibeCheck** acts as a bridge between Slack and your local server. Execute code, generate visualizations, and manage files - all from your Slack workspace with a security approval system.

---

### 🚀 Want to use it without any setup?

**Tired of complex server configuration and installation?**
With VibeCheck Cloud, connect to Slack once and start using it immediately. (No GPU server required!)

| **🛠️ Self-Hosted (Open Source)** | **☁️ Cloud / Premium (Waitlist)** |
| :--- | :--- |
| ✅ **Free** (use your own server) | ⚡ **No installation** (sign up and use instantly) |
| 💻 Use your own GPU/CPU resources | 🧠 High-performance Cloud GPU support (coming soon) |
| 🔧 Self-installation & maintenance | ☕ **Zero maintenance** (24/7 uptime) |
| [👇 **See installation guide below**](#quick-start) | [👉 **[Join the Waitlist]**](https://NestozAI.github.io/VibeCheck) |

> 🎁 **Join the waitlist now and get `1 month free` when we launch.**

---

![Architecture](./assets/architecture.png)

## Features

- **Natural Language Coding** - Chat with AI to write, modify, and execute code
- **Image Generation** - Generate charts and visualizations, automatically uploaded to Slack
- **Security Layer** - Path-based access control with approval system
- **Safe System Commands** - Auto-approved read-only commands (nvidia-smi, df, etc.)
- **Session Continuity** - Conversations persist across messages

## Quick Start

### Linux / macOS

```bash
git clone https://github.com/NestozAI/VibeCheck
cd VibeCheck/self-hosted
./setup.sh
./run.sh
```

### Windows

```cmd
git clone https://github.com/NestozAI/VibeCheck
cd VibeCheck\self-hosted
setup.bat
run.bat
```

## Slack App Setup

### Step 1: Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **"Create New App"** → **"From scratch"**
3. Enter App Name (e.g., "VibeCheck") and select your workspace

### Step 2: Enable Socket Mode

1. Navigate to **Settings → Socket Mode**
2. Toggle **Enable Socket Mode** to ON
3. Click **"Generate"** to create an App-Level Token
   - Token Name: `vibecheck-socket`
   - Scope: `connections:write`
4. Copy the token starting with `xapp-...` → This is your `SLACK_APP_TOKEN`

### Step 3: Configure Bot Token Scopes

Navigate to **OAuth & Permissions → Bot Token Scopes** and add:

| Scope | Description |
|-------|-------------|
| `chat:write` | Send messages as the bot |
| `files:write` | Upload images and files |
| `im:history` | Read DM message history |
| `im:read` | Access DM channel info |
| `im:write` | Start direct messages |
| `users:read` | View user information |

### Step 4: Enable Events

1. Navigate to **Event Subscriptions**
2. Toggle **Enable Events** to ON
3. Under **Subscribe to bot events**, add:
   - `message.im` - Receive DM messages
   - `app_mention` - Respond to @mentions
   - `app_home_opened` - Show home tab

### Step 5: Enable Interactivity

1. Navigate to **Interactivity & Shortcuts**
2. Toggle **Interactivity** to ON

### Step 6: Enable App Home

1. Navigate to **App Home**
2. Enable **Home Tab** and **Messages Tab**
3. Check **"Allow users to send Slash commands and messages from the messages tab"**

### Step 7: Install App to Workspace

1. Navigate to **OAuth & Permissions**
2. Click **"Install to Workspace"**
3. Copy the **Bot User OAuth Token** (`xoxb-...`) → This is your `SLACK_BOT_TOKEN`

### Step 8: Configure Environment

Create `.env` file in `self-hosted/` directory:

```bash
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here
WORK_DIR=/path/to/your/project
```

## Security System

![Security Flow](./assets/security_flow.png)

VibeCheck includes a path-based security system to protect your file system.

### How It Works

1. **Trusted Paths**: Only the `WORK_DIR` is trusted by default
2. **Path Detection**: When you mention a path outside trusted directories, the bot detects it
3. **Approval UI**: A Block Kit message appears with approval options:
   - **Approve & Execute** - One-time access
   - **Approve (Permanent)** - Add path to trusted list
   - **Deny** - Cancel the request

### Safe System Commands

These read-only commands are auto-approved:

```
nvidia-smi, df, free, uptime, whoami, hostname,
cat /proc/cpuinfo, cat /proc/meminfo, ps, top,
ls, pwd, date, which, echo
```

### Bot Commands

| Command | Description |
|---------|-------------|
| `help` | Show help message |
| `reset` | Start a new conversation |
| `/paths` | View trusted paths list |
| `/trust /path` | Add path to trusted list |

## Usage Examples

### Basic Coding

```
User: Show me the current file structure

Bot: 📂 Project structure:
     ├── src/
     │   ├── index.ts
     │   └── utils.ts
     └── package.json
```

### Data Visualization

```
User: Plot y=x², y=2x, and y=3 on the same graph

Bot: [Uploads graph image]
     📊 Generated image: quadratic_comparison.png
```

### System Monitoring

```
User: Check GPU status

Bot: nvidia-smi output:
     +------------------------------------------+
     | NVIDIA-SMI 525.85.12  CUDA Version: 12.0 |
     ...
```

### Security Approval

```
User: Read the logs in /var/log/myapp/

Bot: ⚠️ Security Warning
     AI is trying to access:
     • /var/log/myapp/

     [✅ Approve & Execute] [✅ Approve (Permanent)] [❌ Deny]
```

## Requirements

- Python 3.8+
- AI Coding CLI tool
- Slack Workspace

## File Structure

```
VibeCheck/
├── self-hosted/
│   ├── main.py          # Main bot application
│   ├── cleaner.py       # Output formatting
│   ├── setup.sh         # Installation script
│   ├── run.sh           # Run script
│   └── .env             # Environment variables
├── assets/
│   ├── architecture.png
│   └── security_flow.png
└── README.md
```

## Troubleshooting

### Bot not responding to DMs
- Check **Event Subscriptions** → `message.im` is subscribed
- Check **App Home** → Messages Tab is enabled

### Image upload failing
- Add `files:write` scope and reinstall app

### Path approval buttons not working
- Enable **Interactivity** in Slack App settings

## License

MIT

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.
