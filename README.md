# VibeCheck

> **Run Claude Code on your server. Access it from anywhere.**

[![English](https://img.shields.io/badge/Language-English-blue)](./README.md)
[![Korean](https://img.shields.io/badge/Language-한국어-red)](./README_kr.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![npm](https://img.shields.io/npm/v/vibecheck-agent?color=green)](https://www.npmjs.com/package/vibecheck-agent)

VibeCheck runs a Claude Code agent on your server 24/7. You connect from any device — laptop, phone, tablet — through a web browser. Your computer doesn't need to be on. Sessions persist across devices: start coding on your PC, continue from your phone, pick it back up on your laptop.

<p align="center">
  <img src="./assets/demo.gif" alt="VibeCheck Demo" width="600"/>
</p>

---

## Why VibeCheck?

### Your server never sleeps
Claude Code runs headless on your server as a background service. Close your laptop, go home — the agent keeps running. Come back tomorrow and pick up where you left off.

### Code from any device
Open a browser, connect to your agent. Works on desktop, mobile, any device with a web browser. No app to install.

### Sessions follow you
Start a conversation on your PC, resume it from your phone. Browse all your Claude Code projects and sessions. The same `.jsonl` history is shared — CLI and web see the same conversation.

---

## Quick Start

### Cloud (Easiest)

1. Visit [vibecheck.sotaaz.com](https://vibecheck.sotaaz.com) and sign in
2. Run the install command on your server:

```bash
curl -sL https://vibecheck.sotaaz.com/install/YOUR_API_KEY | bash
```

3. Open Chat and start coding.

### Self-Hosted (Free)

```bash
git clone https://github.com/NestozAI/VibeCheck
cd VibeCheck/self-hosted
./setup.sh
# Open http://localhost:8501
```

See [Self-Hosted Guide](./docs/self-hosted.md) for Slack integration and advanced setup.

### Agent Only

```bash
npm i -g vibecheck-agent
vibecheck-agent --key YOUR_API_KEY --dir /path/to/project
```

---

## Features

### Multi-Device Access
- **Web UI** — Full chat interface in your browser, works on mobile
- **Session Resume** — Pick up any previous conversation from any device
- **Browse All Projects** — Discover all Claude Code projects on the server, switch between them
- **Cross-Device History** — Web conversations appear in CLI, and vice versa

### Real-Time Coding
- **Streaming Responses** — See Claude's output token-by-token as it generates
- **Tool Visualization** — Watch Claude work: "Reading file...", "Running command...", "Editing code..."
- **Image Upload** — Drag & drop screenshots and images directly into the chat
- **Visual Feedback** — Auto-generated project preview screenshots

### Agent Management
- **Skills System** — Switch between agent presets (Research, Coding, Code Review, Test Runner, etc.)
- **Task Scheduler** — Automate recurring tasks with cron (daily git pulls, weekly audits)
- **Model Selection** — Choose Claude model per query (Opus, Sonnet, Haiku)
- **Custom Sub-Agents** — Define specialized agents for multi-agent workflows
- **Cost Tracking** — USD cost and token breakdown for every response

### Security
- **Path-Based Access Control** — Only the working directory is trusted by default
- **Approval UI** — Approve or deny access to paths outside the sandbox
- **Auto-Restart** — Service auto-restarts when the agent package is updated

---

## How It Works

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Your Phone │────▶│  VibeCheck Server │◀────│  Your Laptop    │
│  (browser)  │     │  (WebSocket hub)  │     │  (browser/CLI)  │
└─────────────┘     └────────┬─────────┘     └─────────────────┘
                             │
                    ┌────────▼─────────┐
                    │  Your Server     │
                    │  vibecheck-agent  │
                    │  (Claude Code)   │
                    └──────────────────┘
```

The agent runs Claude Code via the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk). It connects to the server over WebSocket. Web clients connect to the same server. Messages flow both ways in real time.

Session history is stored in `~/.claude/projects/` as `.jsonl` files — the same format Claude Code CLI uses. This means:
- Sessions started from the web are visible in `claude` CLI
- Sessions started from CLI can be resumed from the web
- Browse All Projects discovers every session across all projects

---

## vs Alternatives

| | **VibeCheck** | **Happy Coder** | **Raw SSH** |
|---|---|---|---|
| Claude runs on | **Server** (headless, 24/7) | Your PC (must stay on) | Your PC |
| Access from | Any browser | Mobile app only | Terminal only |
| PC can be off? | **Yes** | No | No |
| Install | `npm i -g` + one command | `npm i -g` + run wrapper | N/A |
| Session sharing | Web + CLI share `.jsonl` | Mobile controls PC session | N/A |
| Open source | MIT | MIT | N/A |
| App required | No (web browser) | Yes (iOS/Android app) | No |

---

## Skills

| Skill | Tools | Purpose |
|-------|-------|---------|
| Research Agent | Read, Grep, Glob, WebSearch, WebFetch | Codebase analysis, info gathering |
| Coding Agent | All tools | Writing & editing code |
| Code Review | Read, Grep, Glob | Bug, security & quality review |
| Test Runner | Read, Glob, Bash | Run tests and summarize |
| Dependency Audit | Read, Glob, Bash | Vulnerability & update checks |
| Git Summary | Read, Bash | Commit history digest |
| Doc Writer | Read, Write, Glob | README and inline docs |

---

## File Structure

```
VibeCheck/
├── cloud/
│   └── agent-ts/              # Cloud agent (npm: vibecheck-agent)
│       └── src/
│           ├── agent.ts       # WebSocket agent, session management
│           ├── claude.ts      # Claude Agent SDK wrapper
│           ├── sessions-scanner.ts  # Project & session discovery
│           ├── skills.ts      # Built-in skill presets
│           ├── scheduler.ts   # Cron-based task scheduler
│           └── security.ts    # Path-based access control
├── self-hosted/               # Self-hosted server + web UI
│   ├── src/
│   │   ├── server.ts          # Express + WebSocket server
│   │   ├── core.ts            # Transport-agnostic orchestration
│   │   └── slack/             # Optional Slack integration
│   └── static/index.html      # Web chat UI
├── assets/                    # README images
├── docs/
│   ├── self-hosted.md         # Self-hosted setup guide
│   └── protocol.md            # WebSocket protocol reference
└── README.md
```

---

## Requirements

- Node.js 18+
- Claude Code CLI (`claude` in PATH)
- Web browser

---

## Troubleshooting

**Agent not connecting?**
- Verify your API key is correct
- Ensure `claude` CLI is installed and in PATH
- Check firewall rules (WebSocket port must be open)

**No responses?**
- Confirm the agent process is running (`systemctl status vibecheck-agent`)
- Check agent logs: `journalctl -u vibecheck-agent -f`

---

## License

MIT

## Contributing

Issues and pull requests are welcome!

---

<p align="center">
  <a href="https://vibecheck.sotaaz.com">
    <img src="https://img.shields.io/badge/Try_VibeCheck-00ff00?style=for-the-badge" alt="Try VibeCheck">
  </a>
</p>
