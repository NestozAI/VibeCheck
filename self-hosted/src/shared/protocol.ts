/**
 * Shared protocol types used by claude.ts
 * (Subset of cloud agent-ts protocol types needed by shared modules)
 */

/** Definition of a custom sub-agent for multi-agent workflows */
export interface AgentDef {
  description: string;
  prompt: string;
  tools?: string[];
  disallowedTools?: string[];
}
