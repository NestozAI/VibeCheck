# VibeCheck

> **Remote control Claude Code from anywhere.**

[![English](https://img.shields.io/badge/Language-English-blue)](./README.md)
[![Korean](https://img.shields.io/badge/Language-한국어-red)](./README_kr.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![TypeScript](https://img.shields.io/badge/TypeScript-Agent-blue.svg)](./cloud/agent-ts/)
[![PyPI](https://img.shields.io/pypi/v/vibecheck-agent?color=green)](https://pypi.org/project/vibecheck-agent/)

**VibeCheck** lets you control Claude Code CLI running on your server via web browser. Write and edit code from anywhere — home, cafe, or on the go.

---

## Choose Your Version

| **🛠️ Self-Hosted (Open Source)** | **☁️ Cloud Version** |
| :--- | :--- |
| ✅ **Free** - use your own server | ⚡ **No server setup** - just install and go |
| 💻 Full control over your environment | 🌐 Web-based chat interface |
| 🔧 Self-installation & maintenance | 📦 `pip install vibecheck-agent` |
| [👇 **See installation guide below**](#self-hosted-setup) | [👉 **Get Started**](https://vibecheck.nestoz.co) |

---

## Features

- **Natural Language Coding** — Chat with Claude to write, modify, and execute code
- **Real-Time Streaming** — See Claude's response token-by-token as it's generated
- **Tool Visualization** — Watch which tools Claude is using in real time ("Reading file…", "Running command…")
- **Skills System** — Select specialized agent presets that change Claude's behavior and tool access
- **Task Scheduler** — Automate recurring tasks with cron expressions (daily git pulls, weekly dependency audits, etc.)
- **Visual Feedback** — Auto-generated HTML/project preview screenshots sent in chat
- **Image Upload** — Drag & drop images directly in the chat window
- **Security Layer** — Path-based access control with one-time or permanent approval
- **Session Continuity** — Conversations persist across messages and reconnects
- **Cost Tracking** — Every response includes USD cost and token breakdown (input/output/cache)
- **Model Selection** — Switch between Claude models per query
- **Custom System Prompt** — Inject a system prompt for any individual query
- **Custom Sub-Agents** — Define named agents (via the Task tool) for multi-agent workflows

---

## Cloud Version

The easiest way to use VibeCheck. No server setup needed!

### Quick Start

#### 1. Sign In
Visit [vibecheck.nestoz.co](https://vibecheck.nestoz.co) and sign in with your email.

#### 2. Install & Run Agent
Copy the one-liner curl command from dashboard and run it on your server:
```bash
curl -sL https://vibecheck.nestoz.co/install/YOUR_API_KEY | bash
```

That's it! Open the Chat page and start coding.

### Agent Options

```bash
vibecheck-agent --key YOUR_API_KEY --dir /path/to/project

Options:
  --key    Your VibeCheck API key (vibe_sk_...)
  --dir    Working directory (default: current directory)
  --server Custom server URL (optional)
```

> **TypeScript agent** (`cloud/agent-ts/`) is the actively maintained implementation. The Python agent (`vibecheck-agent` on PyPI) is the legacy version.

---

## Skills System

Skills are agent presets — each one configures Claude's system prompt and tool permissions for a specific job.

| Skill | Tools | Purpose |
|-------|-------|---------|
| 🔭 Research Agent | Read, Grep, Glob, WebSearch, WebFetch | Codebase analysis, info gathering |
| 💻 Coding Agent | All tools | Writing & editing code |
| 🔍 Code Review | Read, Grep, Glob | Bug, security & quality review |
| 🧪 Test Runner | Read, Glob, Bash | Run tests and summarize results |
| 📦 Dependency Audit | Read, Glob, Bash | Vulnerability & update checks |
| 📋 Git Summary | Read, Bash | Commit history digest |
| 📝 Doc Writer | Read, Write, Glob | README and inline docs |

The web UI sends `skill_id` with the query. The agent fetches the matching preset and applies it for that request only.

---

## Task Scheduler

Automate tasks on a cron schedule:

```jsonc
// Server → Agent
{ "type": "schedule_add", "cron": "0 9 * * 1-5", "message": "Run tests and report failures", "skill_id": "test-runner" }

// Agent fires every weekday at 9 AM, sends result to web UI automatically
```

Schedules persist to `~/.vibecheck/schedules.json` and survive agent restarts. If a user query is in progress when a schedule fires, the task is queued and runs immediately after.

---

## WebSocket Protocol

The TypeScript agent communicates with the server over WebSocket. All messages are JSON.

### Agent → Server

| Message | Description |
|---------|-------------|
| `response` | Final answer with `result`, `cost_usd`, `num_turns`, `usage` (token breakdown), optional `images` |
| `streaming_chunk` | Incremental text delta (`delta`, `index`) — emitted while Claude is generating |
| `tool_status` | Tool start/end event with `tool`, `status`, `label`, optional `detail` |
| `approval_required` | Requests user approval for out-of-scope paths |
| `session_sync` | Reports current `work_dir` and `session_id` on connect |
| `session_update` | Notifies server when session ID changes |
| `skill_list_response` | Returns all available skill presets |
| `schedule_list_response` | Returns all scheduled tasks |
| `schedule_add_response` | Result of adding a new task |
| `ping` / `pong` | Keepalive |

### Server → Agent

| Message | Description |
|---------|-------------|
| `query` | Run a query — supports `model`, `skill_id`, `system_prompt`, `agents` |
| `approval` | User's response to an approval request |
| `interrupt` | Abort the current query |
| `add_trusted_path` | Permanently trust a file path |
| `skill_list` | Request the list of available skills |
| `schedule_add` | Add a new scheduled task |
| `schedule_remove` | Remove a task by ID |
| `schedule_toggle` | Enable or disable a task |
| `schedule_list` | Request all scheduled tasks |
| `session_info` | Sync session ID from server |
| `ping` / `pong` | Keepalive |

### `query` message fields

```jsonc
{
  "type": "query",
  "message": "Refactor the auth module",
  "model": "claude-opus-4-5",         // optional — model override
  "skill_id": "coding",               // optional — skill preset
  "system_prompt": "Reply in Korean", // optional — per-query system prompt
  "agents": {                         // optional — custom sub-agents
    "reviewer": {
      "description": "Code quality reviewer",
      "prompt": "Focus on security and correctness",
      "tools": ["Read", "Grep"]
    }
  }
}
```

---

## Security System

VibeCheck includes a path-based security system to protect your file system.

![Security Flow](./assets/security_flow.png)

### How It Works

1. **Trusted Paths** — Only the working directory is trusted by default
2. **Path Detection** — When Claude tries to access paths outside trusted directories, the agent intercepts it
3. **Approval UI** — An approval request appears in the web UI:
   - **Approve** — One-time access
   - **Approve (Permanent)** — Add to trusted paths list
   - **Deny** — Cancel the operation

### Auto-Approved Commands

These read-only system commands are always allowed:

```
nvidia-smi, df, free, uptime, whoami, hostname,
cat /proc/cpuinfo, cat /proc/meminfo, ps, top,
ls, pwd, date, which, echo
```

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

<details>
<summary>Slack App Configuration Guide</summary>

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
   - `message.im`
   - `app_mention`
   - `app_home_opened`

#### Step 5–7: Interactivity, App Home, Install

1. **Interactivity & Shortcuts** → Enable Interactivity
2. **App Home** → Enable Home Tab and Messages Tab; allow slash commands
3. **OAuth & Permissions** → Install to Workspace; copy `xoxb-...` Bot Token

#### Step 8: Configure Environment

Create `.env` in `self-hosted/`:

```bash
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here
WORK_DIR=/path/to/your/project
```

</details>

---

## File Structure

```
VibeCheck/
├── cloud/
│   ├── agent-ts/            # TypeScript agent (actively maintained)
│   │   └── src/
│   │       ├── agent.ts     # Main WebSocket agent, skill & scheduler integration
│   │       ├── claude.ts    # Claude Agent SDK wrapper (streaming, tools, sessions)
│   │       ├── protocol.ts  # WebSocket message type definitions
│   │       ├── skills.ts    # Built-in skill presets
│   │       ├── scheduler.ts # Cron-based task scheduler
│   │       └── security.ts  # Path-based access control
│   └── agent/               # Python agent (legacy, vibecheck-agent on PyPI)
├── self-hosted/
│   ├── main.py              # Self-hosted Slack bot
│   ├── setup.sh
│   └── run.sh
├── assets/
│   ├── architecture.png
│   ├── ux_demo.png
│   └── security_flow.png
└── README.md
```

---

## Requirements

- Node.js 18+ (TypeScript agent) or Python 3.8+ (legacy agent)
- Claude Code CLI (`claude` command in PATH)
- Web browser (Cloud version) or Slack workspace (Self-hosted)

---

## Troubleshooting

### Agent not connecting
- Check your API key is correct
- Ensure `claude` CLI is installed and in PATH
- Check internet connection and firewall rules

### Not receiving responses
- (Cloud) Make sure the agent process is running; check the Chat page
- (Self-hosted) Verify **Event Subscriptions** → `message.im` is subscribed

### Screenshot not generating
- TypeScript agent: `npx playwright install chromium`
- Python agent: `pip install playwright && playwright install chromium`

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
