import { createHash } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
  unlinkSync,
} from "node:fs";
import path from "node:path";
import { SESSION_DIR } from "./config.js";

interface SessionData {
  work_dir: string;
  session_id: string;
  updated_at: string;
}

export function getSessionFilePath(workDir: string): string {
  const hash = createHash("md5").update(workDir).digest("hex").slice(0, 12);
  return path.join(SESSION_DIR, `session_${hash}.json`);
}

export function saveSessionId(workDir: string, sessionId: string): void {
  try {
    if (!existsSync(SESSION_DIR)) {
      mkdirSync(SESSION_DIR, { recursive: true });
    }
    const data: SessionData = {
      work_dir: workDir,
      session_id: sessionId,
      updated_at: new Date().toISOString(),
    };
    writeFileSync(getSessionFilePath(workDir), JSON.stringify(data, null, 2));
    console.log(`[session] 세션 ID 저장: ${sessionId.slice(0, 20)}...`);
  } catch (e) {
    console.error(`[session] 세션 ID 저장 실패:`, e);
  }
}

export function loadSessionId(workDir: string): string | null {
  try {
    const filePath = getSessionFilePath(workDir);
    if (!existsSync(filePath)) return null;
    const raw = readFileSync(filePath, "utf-8");
    const data: SessionData = JSON.parse(raw);
    if (data.session_id && data.work_dir === workDir) {
      console.log(
        `[session] 세션 ID 로드: ${data.session_id.slice(0, 20)}...`,
      );
      return data.session_id;
    }
    return null;
  } catch {
    return null;
  }
}

export function clearSessionId(workDir: string): void {
  try {
    const filePath = getSessionFilePath(workDir);
    if (existsSync(filePath)) {
      unlinkSync(filePath);
      console.log("[session] 세션 ID 삭제됨");
    }
  } catch {
    // ignore
  }
}
