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
}

/**
 * Encode a filesystem path to Claude Code's project directory name.
 * /disk1/lecture/foo → -disk1-lecture-foo
 */
function encodeProjectPath(projectPath: string): string {
  return projectPath.replace(/\//g, "-");
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

  // Fast path: sessions-index.json
  const indexPath = path.join(projectDir, "sessions-index.json");
  if (fs.existsSync(indexPath)) {
    try {
      const data = JSON.parse(fs.readFileSync(indexPath, "utf-8"));
      if (data.entries && Array.isArray(data.entries)) {
        return data.entries
          .filter((e: Record<string, unknown>) => !e.isSidechain)
          .map((e: Record<string, unknown>) => ({
            sessionId: e.sessionId as string,
            firstPrompt: (e.firstPrompt as string) || "",
            messageCount: (e.messageCount as number) || 0,
            created: (e.created as string) || "",
            modified: (e.modified as string) || "",
            gitBranch: e.gitBranch as string | undefined,
            projectPath: (e.projectPath as string) || workDir,
          }))
          .sort(
            (a: ClaudeCodeSession, b: ClaudeCodeSession) =>
              new Date(b.modified).getTime() - new Date(a.modified).getTime(),
          )
          .slice(0, 50);
      }
    } catch {
      // Fall through to JSONL scan
    }
  }

  // Fallback: scan JSONL files
  const sessions: ClaudeCodeSession[] = [];
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

      sessions.push({
        sessionId,
        firstPrompt,
        messageCount: 0,
        created,
        modified: stats.mtime.toISOString(),
        gitBranch,
        projectPath: workDir,
      });
    }
  } catch {
    // Directory read failed
  }

  return sessions;
}
