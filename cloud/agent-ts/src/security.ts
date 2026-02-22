import path from "node:path";
import type { PermissionResult } from "@anthropic-ai/claude-agent-sdk";
import { SAFE_SYSTEM_COMMANDS } from "./config.js";

// Regex patterns to extract paths from text
const ABSOLUTE_PATH_RE = /(?:^|\s)(\/[^\s:*?"<>|]+)/g;
const RELATIVE_PATH_RE = /(?:^|\s)(\.\.?\/[^\s:*?"<>|]+)/g;

export class SecurityManager {
  private trustedPaths: Set<string>;
  private pendingApproval: {
    resolve: (result: PermissionResult) => void;
    toolName: string;
    input: Record<string, unknown>;
  } | null = null;

  /** Callback to send approval_required to WebSocket */
  onApprovalNeeded?: (
    paths: string[],
    toolName: string,
    input: Record<string, unknown>,
  ) => void;

  constructor(workDir: string) {
    this.trustedPaths = new Set([path.resolve(workDir)]);
  }

  addTrustedPath(p: string): void {
    const normalized = path.resolve(p);
    this.trustedPaths.add(normalized);
    console.log(`[security] 신뢰 경로 추가: ${normalized}`);
  }

  isPathTrusted(p: string): boolean {
    const normalized = path.resolve(p);
    for (const trusted of this.trustedPaths) {
      if (
        normalized === trusted ||
        normalized.startsWith(trusted + path.sep)
      ) {
        return true;
      }
    }
    return false;
  }

  isSafeCommand(command: string): boolean {
    const trimmed = command.trim();
    for (const safe of SAFE_SYSTEM_COMMANDS) {
      if (trimmed === safe || trimmed.startsWith(safe + " ")) {
        return true;
      }
    }
    return false;
  }

  /**
   * SDK canUseTool callback.
   * Matches the exact CanUseTool signature from @anthropic-ai/claude-agent-sdk.
   */
  canUseTool = async (
    toolName: string,
    input: Record<string, unknown>,
    options: { signal: AbortSignal },
  ): Promise<PermissionResult> => {
    const paths = this.extractPathsFromToolInput(toolName, input);
    const untrusted = paths.filter((p) => !this.isPathTrusted(p));

    // Trusted paths or safe commands → allow immediately
    if (untrusted.length === 0) {
      return { behavior: "allow", updatedInput: input };
    }

    if (
      toolName === "Bash" &&
      typeof input.command === "string" &&
      this.isSafeCommand(input.command)
    ) {
      return { behavior: "allow", updatedInput: input };
    }

    // Request approval from web UI via WebSocket
    this.onApprovalNeeded?.(untrusted, toolName, input);

    // Wait for user response (Promise resolved by resolveApproval)
    return new Promise<PermissionResult>((resolve) => {
      this.pendingApproval = { resolve, toolName, input };

      // Handle abort signal
      options.signal.addEventListener(
        "abort",
        () => {
          this.pendingApproval = null;
          resolve({ behavior: "deny", message: "Operation aborted" });
        },
        { once: true },
      );
    });
  };

  /**
   * Called by agent when approval/denial arrives from server.
   */
  resolveApproval(approved: boolean, permanent: boolean): void {
    if (!this.pendingApproval) return;
    const { resolve, toolName, input } = this.pendingApproval;

    if (approved) {
      if (permanent) {
        const paths = this.extractPathsFromToolInput(toolName, input);
        paths.forEach((p) => this.addTrustedPath(p));
      }
      resolve({ behavior: "allow", updatedInput: input });
    } else {
      resolve({ behavior: "deny", message: "사용자가 거부했습니다" });
    }
    this.pendingApproval = null;
  }

  private extractPathsFromToolInput(
    toolName: string,
    input: Record<string, unknown>,
  ): string[] {
    switch (toolName) {
      case "Read":
      case "Write":
      case "Edit":
        return typeof input.file_path === "string" ? [input.file_path] : [];
      case "Bash":
        return typeof input.command === "string"
          ? extractPathsFromText(input.command)
          : [];
      case "Glob":
      case "Grep":
        return typeof input.path === "string" ? [input.path] : [];
      default:
        return [];
    }
  }
}

/** Extract absolute paths from text (for Bash commands, user messages, etc.) */
export function extractPathsFromText(text: string): string[] {
  const paths: string[] = [];
  let match: RegExpExecArray | null;

  ABSOLUTE_PATH_RE.lastIndex = 0;
  while ((match = ABSOLUTE_PATH_RE.exec(text)) !== null) {
    paths.push(match[1]);
  }

  RELATIVE_PATH_RE.lastIndex = 0;
  while ((match = RELATIVE_PATH_RE.exec(text)) !== null) {
    paths.push(match[1]);
  }

  return paths;
}
