# WebSocket Protocol Reference

The TypeScript agent communicates with the server over WebSocket. All messages are JSON.

## Agent → Server

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
| `project_list` | Returns all discoverable Claude Code projects |
| `project_sessions` | Returns sessions for a specific project |
| `claude_sessions` | Returns CLI sessions for the agent's working directory |
| `ping` / `pong` | Keepalive |

## Server → Agent

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
| `resume_session` | Resume a previous session (with optional `projectPath` for cross-project) |
| `discover_projects` | Scan all Claude Code projects on the server |
| `scan_project` | Get sessions for a specific project path |
| `ping` / `pong` | Keepalive |

## `query` message fields

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

## Security Flow

![Security Flow](../assets/security_flow.png)

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
