# VibeCheck

Control your server's AI coding assistant remotely via Slack. Execute code, generate visualizations, and manage files - all from your Slack workspace.

```
[Slack] <---> [Your Server] <---> [AI Coding Assistant]
   DM chat      Agent runs       Code modifications
```

## Features

- **Natural Language Coding**: Chat with AI to write, modify, and execute code
- **Image Generation**: Generate charts and visualizations, automatically uploaded to Slack
- **Security Layer**: Path-based access control with approval system
- **Safe System Commands**: Auto-approved read-only commands (nvidia-smi, df, etc.)
- **Session Continuity**: Conversations persist across messages

## Quick Start

### Self-Hosted (Free)

```bash
git clone https://github.com/NestozAI/VibeCheck
cd VibeCheck/self-hosted
./setup.sh
./run.sh
```

## Slack App Setup (Detailed)

### Step 1: Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **"Create New App"** → **"From scratch"**
3. Enter App Name (e.g., "VibeCheck") and select your workspace

### Step 2: Enable Socket Mode

1. Navigate to **Settings → Socket Mode**
2. Toggle **Enable Socket Mode** to ON
3. Click **"Generate"** to create an App-Level Token
   - Token Name: `vibecheck-socket` (or any name)
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

### Step 5: Enable Interactivity (for approval buttons)

1. Navigate to **Interactivity & Shortcuts**
2. Toggle **Interactivity** to ON
3. (Socket Mode handles the request URL automatically)

### Step 6: Enable App Home

1. Navigate to **App Home**
2. Under **Show Tabs**, enable:
   - **Home Tab** - ON
   - **Messages Tab** - ON
   - Check **"Allow users to send Slash commands and messages from the messages tab"**

### Step 7: Install App to Workspace

1. Navigate to **OAuth & Permissions**
2. Click **"Install to Workspace"**
3. Authorize the app
4. Copy the **Bot User OAuth Token** starting with `xoxb-...` → This is your `SLACK_BOT_TOKEN`

### Step 8: Configure Environment

Create `.env` file in `self-hosted/` directory:

```bash
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here
WORK_DIR=/path/to/your/project
```

## Security System

VibeCheck includes a path-based security system to protect your file system.

### How It Works

1. **Trusted Paths**: Only the `WORK_DIR` is trusted by default
2. **Path Detection**: When you mention a path outside trusted directories, the bot detects it
3. **Approval UI**: A Block Kit message appears with approval options:
   - **Approve & Execute** - One-time access
   - **Approve (Permanent)** - Add path to trusted list
   - **Deny** - Cancel the request

### Safe System Commands

These read-only commands are auto-approved (no user confirmation needed):

```
nvidia-smi, df, free, uptime, whoami, hostname,
cat /proc/cpuinfo, cat /proc/meminfo, ps, top,
ls, pwd, date, which, echo
```

### Bot Commands

| Command | Description |
|---------|-------------|
| `help` or `/help` | Show help message |
| `reset` or `/reset` | Start a new conversation |
| `/paths` | View trusted paths list |
| `/trust /path/to/folder` | Add path to trusted list |

### Example Interaction

```
User: Read the logs in /var/log/myapp/

Bot: ⚠️ Security Warning
     AI is trying to access:
     • `/var/log/myapp/`

     [✅ Approve & Execute] [✅ Approve (Permanent)] [❌ Deny]

User: (clicks Approve)

Bot: ⏳ Approved! Running...
Bot: Here are the log contents: [...]
```

## Usage Examples

### Basic Coding

```
User: Show me the current file structure

Bot: 📂 Project structure:
     ├── src/
     │   ├── index.ts
     │   └── utils.ts
     └── package.json

User: Add logging to index.ts

Bot: ✅ Logging added!
     [Shows changes]
```

### Data Visualization

```
User: Plot y=x², y=2x, and y=3 on the same graph

Bot: [Generates and uploads graph image]
     📊 Generated image: `quadratic_comparison.png`
```

### System Monitoring

```
User: Check GPU status

Bot: nvidia-smi output:
     +-----------------------------------------------------------------------------+
     | NVIDIA-SMI 525.85.12    Driver Version: 525.85.12    CUDA Version: 12.0     |
     | GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
     ...
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Slack                                 │
│  ┌─────────┐                              ┌─────────┐       │
│  │   DM    │ ────── Socket Mode ───────▶ │   Bot   │       │
│  └─────────┘                              └────┬────┘       │
└───────────────────────────────────────────────┼─────────────┘
                                                │
┌───────────────────────────────────────────────┼─────────────┐
│                    Your Server                 │             │
│                                               ▼             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  main.py                             │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │   │
│  │  │  Security   │  │   Image     │  │   Claude    │  │   │
│  │  │   Layer     │  │   Upload    │  │   Runner    │  │   │
│  │  └─────────────┘  └─────────────┘  └──────┬──────┘  │   │
│  └───────────────────────────────────────────┼──────────┘   │
│                                               │             │
│                                               ▼             │
│                                    ┌─────────────────┐      │
│                                    │  AI CLI Tool    │      │
│                                    │  (subprocess)   │      │
│                                    └─────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

## Requirements

- Python 3.8+
- AI Coding CLI tool
- Slack Workspace (with app creation permissions)

## File Structure

```
VibeCheck/
├── self-hosted/
│   ├── main.py          # Main bot application
│   ├── cleaner.py       # Output formatting utilities
│   ├── setup.sh         # Installation script
│   ├── run.sh           # Run script
│   ├── requirements.txt # Python dependencies
│   └── .env             # Environment variables (create this)
├── docs/
│   └── self-hosted.md   # Detailed documentation
└── README.md
```

## Troubleshooting

### Bot not responding to DMs

1. Check **Event Subscriptions** → `message.im` is subscribed
2. Check **App Home** → Messages Tab is enabled
3. Verify Socket Mode is enabled and connected

### Image upload failing

1. Add `files:write` scope in OAuth & Permissions
2. Click **"Reinstall App"** after adding scope

### "missing_scope" error

1. Add the required scope mentioned in the error
2. Reinstall the app to your workspace
3. Restart the bot

### Path approval not working

1. Enable **Interactivity** in Slack App settings
2. Socket Mode handles this automatically - no URL needed

## License

MIT

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.
