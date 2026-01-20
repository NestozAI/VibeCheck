# VibeCheck

> **Remote control Claude Code from anywhere.**

[![English](https://img.shields.io/badge/Language-English-blue)](./README.md)
[![Korean](https://img.shields.io/badge/Language-한국어-red)](./README_kr.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![PyPI](https://img.shields.io/pypi/v/vibecheck-agent?color=green)](https://pypi.org/project/vibecheck-agent/)

**VibeCheck** lets you control Claude Code CLI running on your server via web browser. Write and edit code from anywhere - home, cafe, or on the go.

---

## Choose Your Version

| **🛠️ Self-Hosted (Open Source)** | **☁️ Cloud Version** |
| :--- | :--- |
| ✅ **Free** - use your own server | ⚡ **No server setup** - just install and go |
| 💻 Full control over your environment | 🌐 Web-based chat interface |
| 🔧 Self-installation & maintenance | 📦 `pip install vibecheck-agent` |
| [👇 **See installation guide below**](#self-hosted-setup) | [👉 **Get Started**](https://vibecheck.nestoz.co) |

---

## Self-Hosted Setup

For users who want full control over their server and Slack app.

### Quick Start

#### Linux / macOS

```bash
git clone https://github.com/NestozAI/VibeCheck
cd VibeCheck/self-hosted
./setup.sh
./run.sh
```

#### Windows

```cmd
git clone https://github.com/NestozAI/VibeCheck
cd VibeCheck\self-hosted
setup.bat
run.bat
```

### Slack App Setup (Self-Hosted Only)

<details>
<summary>Click to expand Slack App configuration guide</summary>

#### Step 1: Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **"Create New App"** → **"From scratch"**
3. Enter App Name (e.g., "VibeCheck") and select your workspace

#### Step 2: Enable Socket Mode

1. Navigate to **Settings → Socket Mode**
2. Toggle **Enable Socket Mode** to ON
3. Click **"Generate"** to create an App-Level Token
   - Token Name: `vibecheck-socket`
   - Scope: `connections:write`
4. Copy the token starting with `xapp-...` → This is your `SLACK_APP_TOKEN`

#### Step 3: Configure Bot Token Scopes

Navigate to **OAuth & Permissions → Bot Token Scopes** and add:

| Scope | Description |
|-------|-------------|
| `chat:write` | Send messages as the bot |
| `files:write` | Upload images and files |
| `im:history` | Read DM message history |
| `im:read` | Access DM channel info |
| `im:write` | Start direct messages |
| `users:read` | View user information |

#### Step 4: Enable Events

1. Navigate to **Event Subscriptions**
2. Toggle **Enable Events** to ON
3. Under **Subscribe to bot events**, add:
   - `message.im` - Receive DM messages
   - `app_mention` - Respond to @mentions
   - `app_home_opened` - Show home tab

#### Step 5: Enable Interactivity

1. Navigate to **Interactivity & Shortcuts**
2. Toggle **Interactivity** to ON

#### Step 6: Enable App Home

1. Navigate to **App Home**
2. Enable **Home Tab** and **Messages Tab**
3. Check **"Allow users to send Slash commands and messages from the messages tab"**

#### Step 7: Install App to Workspace

1. Navigate to **OAuth & Permissions**
2. Click **"Install to Workspace"**
3. Copy the **Bot User OAuth Token** (`xoxb-...`) → This is your `SLACK_BOT_TOKEN`

#### Step 8: Configure Environment

Create `.env` file in `self-hosted/` directory:

```bash
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here
WORK_DIR=/path/to/your/project
```

</details>

---

## Cloud Version

The easiest way to use VibeCheck. No server setup needed!

### Quick Start

#### 1. Sign In
Visit [vibecheck.nestoz.co](https://vibecheck.nestoz.co) and sign in with your email.

#### 2. Get Your API Key
Copy your API key from the dashboard.

#### 3. Install & Run Agent
```bash
pip install vibecheck-agent
vibecheck-agent --key YOUR_API_KEY --dir /path/to/your/project
```

That's it! Now open the Chat page and start coding.

### Agent Options

```bash
vibecheck-agent --key YOUR_API_KEY --dir /path/to/project

Options:
  --key    Your VibeCheck API key (vibe_sk_...)
  --dir    Working directory (default: current directory)
  --server Custom server URL (optional)
```

---

## Demo

![Architecture](./assets/architecture.png)

*System Architecture: Web Browser ↔ Cloud Server ↔ Local Agent ↔ Claude Code*

![UX Demo](./assets/ux_demo.png)

*Request UI rendering, design changes, and get instant visual feedback - all from web.*

---

## Features

- **Natural Language Coding** - Chat with Claude Code to write, modify, and execute code
- **Visual Feedback** - Generate UI screenshots and visualizations, displayed in web chat
- **Image Upload** - Upload images directly in chat with drag & drop support
- **Security Layer** - Path-based access control with approval system
- **Session Continuity** - Conversations persist across messages
- **Screenshot Generation** - Automatic HTML/project preview screenshots

---

## Security System

![Security Flow](./assets/security_flow.png)

VibeCheck includes a path-based security system to protect your file system.

### How It Works

1. **Trusted Paths**: Only the working directory is trusted by default
2. **Path Detection**: When Claude tries to access paths outside trusted directories, the bot detects it
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

---

## Usage Examples

### Building UI

```
User: Create a login form with email and password fields, modern dark theme

Bot: I've created index.html with a login form...
     [Uploads screenshot of the rendered UI]
```

### Code Modification

```
User: Add form validation to check email format

Bot: I've added email validation...
     [Uploads updated screenshot]
```

### System Monitoring

```
User: Check GPU status

Bot: nvidia-smi output:
     +------------------------------------------+
     | NVIDIA-SMI 525.85.12  CUDA Version: 12.0 |
     ...
```

---

## Requirements

- Python 3.8+
- Claude Code CLI (`claude` command)
- Web browser (for Cloud version) or Slack Workspace (for Self-hosted)

---

## File Structure

```
VibeCheck/
├── cloud/
│   └── agent/           # PyPI package source (vibecheck-agent)
│       ├── agent.py     # Agent implementation
│       └── html_screenshot.py
├── self-hosted/
│   ├── main.py          # Self-hosted bot
│   ├── setup.sh         # Installation script
│   └── run.sh           # Run script
├── assets/
│   ├── architecture.png
│   ├── ux_demo.png
│   └── security_flow.png
└── README.md
```

---

## Troubleshooting

### Agent not connecting
- Check your API key is correct
- Ensure `claude` CLI is installed and accessible
- Check internet connection

### Not receiving responses
- (Self-hosted) Check **Event Subscriptions** → `message.im` is subscribed
- (Cloud) Make sure Agent is running and check the Chat page

### Screenshot not generating
- Install playwright: `pip install playwright && playwright install chromium`

---

## License

MIT

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

---

<p align="center">
  <a href="https://vibecheck.nestoz.co">
    <img src="https://img.shields.io/badge/Try_VibeCheck_Cloud-00ff00?style=for-the-badge" alt="Try VibeCheck Cloud">
  </a>
</p>
