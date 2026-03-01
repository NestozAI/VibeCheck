/**
 * Scans Claude Code's local session history at ~/.claude/projects/
 * and returns metadata for display in the web UI sidebar.
 */

import fs from "node:fs";
import path from "node:path";
import os from "node:os";

export interface ClaudeCodeSession {
  sessionId: string;
  firstPrompt: string;
  messageCount: number;
  created: string;   // ISO timestamp
  modified: string;  // ISO timestamp
  gitBranch?: string;
  projectPath: string;
  /** Whether the session has displayable conversation content */
  hasConversation: boolean;
}

/**
 * Encode a filesystem path to Claude Code's project directory name.
 * Claude Code replaces /, _, spaces, and non-ASCII chars with dashes.
 * /data/projects/amber_demo → -data-projects-amber-demo
 */
function encodeProjectPath(projectPath: string): string {
  return projectPath.replace(/[/_\s]/g, "-").replace(/[^\x20-\x7E]/g, "-");
}

/**
 * Scan Claude Code sessions for the given workDir.
 * Fast path: reads sessions-index.json if available.
 * Fallback: scans JSONL files and reads first few lines for metadata.
 */
export function scanClaudeCodeSessions(workDir: string): ClaudeCodeSession[] {
  const encoded = encodeProjectPath(workDir);
  const projectDir = path.join(os.homedir(), ".claude", "projects", encoded);

  if (!fs.existsSync(projectDir)) return [];

  // Collect sessions from index
  const indexSessions = new Map<string, ClaudeCodeSession>();
  const indexPath = path.join(projectDir, "sessions-index.json");
  if (fs.existsSync(indexPath)) {
    try {
      const data = JSON.parse(fs.readFileSync(indexPath, "utf-8"));
      if (data.entries && Array.isArray(data.entries)) {
        for (const e of data.entries) {
          if (e.isSidechain) continue;
          const sid = e.sessionId as string;
          indexSessions.set(sid, {
            sessionId: sid,
            firstPrompt: (e.firstPrompt as string) || "",
            messageCount: (e.messageCount as number) || 0,
            created: (e.created as string) || "",
            modified: (e.modified as string) || "",
            gitBranch: e.gitBranch as string | undefined,
            projectPath: (e.projectPath as string) || workDir,
            hasConversation: !!((e.firstPrompt as string)?.trim()) && ((e.messageCount as number) || 0) >= 2,
          });
        }
      }
    } catch {
      // Fall through to JSONL scan
    }
  }

  // Also scan JSONL files to catch sessions not in the (possibly stale) index
  try {
    const files = fs
      .readdirSync(projectDir)
      .filter((f) => f.endsWith(".jsonl"))
      .map((f) => ({
        name: f,
        stats: fs.statSync(path.join(projectDir, f)),
      }))
      .sort((a, b) => b.stats.mtimeMs - a.stats.mtimeMs)
      .slice(0, 50);

    for (const { name, stats } of files) {
      const sessionId = name.replace(".jsonl", "");
      if (indexSessions.has(sessionId)) continue; // Already have from index

      let firstPrompt = "";
      let gitBranch: string | undefined;
      const created = stats.birthtime.toISOString();

      // Read first 4KB to extract metadata from early lines
      try {
        const fd = fs.openSync(path.join(projectDir, name), "r");
        const buf = Buffer.alloc(4096);
        const bytesRead = fs.readSync(fd, buf, 0, 4096, 0);
        fs.closeSync(fd);

        const chunk = buf.toString("utf-8", 0, bytesRead);
        const lines = chunk.split("\n").filter(Boolean);

        for (const line of lines) {
          try {
            const obj = JSON.parse(line);
            if (obj.type === "user" && obj.message?.content) {
              const content = obj.message.content;
              if (Array.isArray(content)) {
                const textPart = content.find(
                  (c: Record<string, unknown>) => c.type === "text",
                );
                if (textPart) firstPrompt = (textPart.text as string).slice(0, 100);
              } else if (typeof content === "string") {
                firstPrompt = content.slice(0, 100);
              }
              if (obj.gitBranch) gitBranch = obj.gitBranch;
              break;
            }
          } catch {
            // Skip unparseable lines
          }
        }
      } catch {
        // Skip unreadable files
      }

      indexSessions.set(sessionId, {
        sessionId,
        firstPrompt,
        messageCount: 0,
        created,
        modified: stats.mtime.toISOString(),
        gitBranch,
        projectPath: workDir,
        hasConversation: !!firstPrompt.trim(),
      });
    }
  } catch {
    // Directory read failed
  }

  return Array.from(indexSessions.values())
    .sort((a, b) => new Date(b.modified).getTime() - new Date(a.modified).getTime())
    .slice(0, 50);
}

/**
 * Lightweight project summary for the "Browse Projects" discovery UI.
 * Does NOT expose session contents — only project path + session count.
 */
export interface ProjectSummary {
  /** The decoded project path (best-effort reverse of encoding) */
  projectPath: string;
  /** Encoded directory name under ~/.claude/projects/ */
  dirName: string;
  /** Number of session JSONL files */
  sessionCount: number;
  /** Most recent session modification time (ISO) */
  lastModified: string;
}

/**
 * Scan ALL Claude Code project directories under ~/.claude/projects/.
 * Returns a lightweight list of projects with session counts.
 * No session content is read — safe for discovery/browsing.
 */
export function scanAllProjects(): ProjectSummary[] {
  const projectsRoot = path.join(os.homedir(), ".claude", "projects");
  if (!fs.existsSync(projectsRoot)) return [];

  const projects: ProjectSummary[] = [];
  try {
    const dirs = fs.readdirSync(projectsRoot, { withFileTypes: true })
      .filter(d => d.isDirectory());

    for (const dir of dirs) {
      const dirPath = path.join(projectsRoot, dir.name);
      try {
        // Count sessions: both .jsonl files and UUID directories (newer Claude Code format)
        const entries = fs.readdirSync(dirPath, { withFileTypes: true });
        const jsonlCount = entries.filter(e => e.isFile() && e.name.endsWith(".jsonl")).length;
        const uuidDirCount = entries.filter(e => e.isDirectory() && /^[0-9a-f]{8}-/.test(e.name)).length;
        const sessionCount = jsonlCount + uuidDirCount;

        if (sessionCount === 0) continue; // Skip projects with no sessions

        // Get latest mtime cheaply: check sessions-index.json or directory mtime
        // (avoids stat-ing every JSONL file — can be 1000+ files)
        let latestMtime = 0;
        try {
          const indexPath = path.join(dirPath, "sessions-index.json");
          if (fs.existsSync(indexPath)) {
            latestMtime = fs.statSync(indexPath).mtimeMs;
          } else {
            latestMtime = fs.statSync(dirPath).mtimeMs;
          }
        } catch { /* fallback: 0 */ }

        // Best-effort decode: replace leading dash + internal dashes back to /
        // e.g. "-disk1-projects-blog" → "/disk1/projects/blog"
        const decoded = dir.name.startsWith("-")
          ? dir.name.replace(/-/g, "/")
          : "/" + dir.name.replace(/-/g, "/");

        projects.push({
          projectPath: decoded,
          dirName: dir.name,
          sessionCount,
          lastModified: latestMtime ? new Date(latestMtime).toISOString() : "",
        });
      } catch { /* skip unreadable dirs */ }
    }
  } catch { /* root dir read failed */ }

  return projects.sort((a, b) =>
    new Date(b.lastModified).getTime() - new Date(a.lastModified).getTime()
  );
}

export interface SessionMessage {
  role: "user" | "assistant";
  content: string;
}

/**
 * Read conversation history from a Claude Code JSONL session file.
 * Extracts user/assistant text messages, skipping tool calls and system messages.
 * Returns the last `limit` messages to keep payload small.
 */
export function readSessionHistory(
  workDir: string,
  sessionId: string,
  limit = 30,
): SessionMessage[] {
  const encoded = encodeProjectPath(workDir);
  const filePath = path.join(
    os.homedir(),
    ".claude",
    "projects",
    encoded,
    `${sessionId}.jsonl`,
  );

  if (!fs.existsSync(filePath)) return [];

  const messages: SessionMessage[] = [];
  try {
    const content = fs.readFileSync(filePath, "utf-8");
    const lines = content.split("\n").filter(Boolean);

    for (const line of lines) {
      try {
        const obj = JSON.parse(line);
        if (obj.type !== "user" && obj.type !== "assistant") continue;

        const role = obj.type as "user" | "assistant";
        const msgContent = obj.message?.content;
        if (!msgContent) continue;

        let text = "";
        if (Array.isArray(msgContent)) {
          const textParts = msgContent
            .filter((c: Record<string, unknown>) => c.type === "text")
            .map((c: Record<string, unknown>) => c.text as string);
          text = textParts.join("\n");
        } else if (typeof msgContent === "string") {
          text = msgContent;
        }

        // Skip empty messages (tool-only responses)
        if (!text.trim()) continue;

        // Truncate very long messages
        if (text.length > 2000) {
          text = text.slice(0, 2000) + "\n\n... (truncated)";
        }

        messages.push({ role, content: text });
      } catch {
        // Skip unparseable lines
      }
    }
  } catch {
    // File read failed
  }

  // Return last N messages
  return messages.slice(-limit);
}
