import path from "node:path";
import { randomUUID } from "node:crypto";
import type { PermissionResult } from "@anthropic-ai/claude-agent-sdk";
import { SAFE_SYSTEM_COMMANDS } from "./config.js";
import { logEffect } from "./effects/log.js";
import {
  APPROVAL_TIMEOUT_MS,
  resolveApprovalReply,
  resolvePermissionGate,
  type ApprovalReply,
} from "./effects/policy.js";

// Regex patterns to extract paths from text
const ABSOLUTE_PATH_RE = /(?:^|\s)(\/[^\s:*?"<>|]+)/g;
const RELATIVE_PATH_RE = /(?:^|\s)(\.\.?\/[^\s:*?"<>|]+)/g;

export class SecurityManager {
  private trustedPaths: Set<string>;
  private pendingApproval: {
    resolve: (result: PermissionResult) => void;
    toolName: string;
    input: Record<string, unknown>;
    triggerId: string;
    timer: ReturnType<typeof setTimeout>;
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
    console.log(`[security] Trusted path added: ${normalized}`);
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

    // Branch decision lives in the pure policy (effects/policy.ts) — no ad-hoc ifs here
    const gate = resolvePermissionGate({
      trust: untrusted.length === 0 ? "trusted" : "untrusted",
      tool:
        toolName === "Bash" &&
        typeof input.command === "string" &&
        this.isSafeCommand(input.command)
          ? "safe-bash"
          : "other",
    });
    if (gate.kind === "allow") {
      return { behavior: "allow", updatedInput: input };
    }

    // Request approval from web UI via WebSocket
    const triggerId = randomUUID();
    logEffect({
      effect: "approval-gate",
      trigger_id: triggerId,
      outcome: "trigger",
      detail: toolName,
    });
    this.onApprovalNeeded?.(untrusted, toolName, input);

    // Wait for user response — resolved by resolveApproval / abort / timeout (B2 fix)
    return new Promise<PermissionResult>((resolve) => {
      const timer = setTimeout(
        () => this.settleApproval("timeout"),
        APPROVAL_TIMEOUT_MS,
      );
      this.pendingApproval = { resolve, toolName, input, triggerId, timer };

      options.signal.addEventListener(
        "abort",
        () => this.settleApproval("abort"),
        { once: true },
      );
    });
  };

  /**
   * Called by agent when approval/denial arrives from server.
   */
  resolveApproval(approved: boolean, permanent: boolean): void {
    this.settleApproval(
      approved ? (permanent ? "allow-permanent" : "allow") : "deny",
    );
  }

  /** 승인 대기의 유일한 종결 지점 — 모든 경로가 sent|skipped(reason)으로 기록된다 */
  private settleApproval(reply: ApprovalReply): void {
    if (!this.pendingApproval) return;
    const { resolve, toolName, input, triggerId, timer } = this.pendingApproval;
    clearTimeout(timer);
    this.pendingApproval = null;

    const decision = resolveApprovalReply(reply);
    if (decision.kind === "allow") {
      if (decision.persist) {
        const paths = this.extractPathsFromToolInput(toolName, input);
        paths.forEach((p) => this.addTrustedPath(p));
      }
      logEffect({
        effect: "approval-gate",
        trigger_id: triggerId,
        outcome: "sent",
        reason: reply,
      });
      resolve({ behavior: "allow", updatedInput: input });
    } else {
      logEffect({
        effect: "approval-gate",
        trigger_id: triggerId,
        outcome: "skipped",
        reason: decision.reason,
      });
      const message =
        decision.reason === "user-denied"
          ? "User denied the request"
          : decision.reason === "approval-timeout"
            ? `Approval request timed out after ${APPROVAL_TIMEOUT_MS / 60_000} minutes`
            : "Operation aborted";
      resolve({ behavior: "deny", message });
    }
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
