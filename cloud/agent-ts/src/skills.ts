/**
 * Skills System
 *
 * A skill is a named preset that combines:
 * - systemPrompt override  → specialises Claude's behaviour
 * - allowedTools override  → restricts/expands what Claude may do
 *
 * Agent types (read-only research vs. full coding) are expressed as skills.
 */

export interface Skill {
    id: string;
    name: string;
    icon: string;
    description: string;
    /** Prepended / appended to Claude's default system prompt */
    systemPrompt?: string;
    /**
     * If set, only these tools are available for this skill.
     * Leave undefined to inherit the global allowedTools list.
     */
    allowedTools?: string[];
}

// ---------------------------------------------------------------------------
// Built-in skills
// ---------------------------------------------------------------------------

export const DEFAULT_SKILLS: Skill[] = [
    // ── Agent types ──────────────────────────────────────────────────────────

    {
        id: "research",
        name: "Research Agent",
        icon: "🔭",
        description: "Read-only — optimized for code analysis, documentation search, and information gathering",
        systemPrompt:
            "You are a research agent. You ONLY read and analyse — never modify files. " +
            "Provide detailed, well-structured summaries and insights.",
        allowedTools: ["Read", "Glob", "Grep", "WebFetch", "WebSearch"],
    },
    {
        id: "coding",
        name: "Coding Agent",
        icon: "💻",
        description: "File modification enabled — optimized for coding, refactoring, and bug fixes",
        systemPrompt:
            "You are an expert software engineer. Write clean, well-tested, idiomatic code. " +
            "Explain every change you make.",
        // No allowedTools restriction — uses the global list
    },

    // ── Quick-action skills ───────────────────────────────────────────────────

    {
        id: "code-review",
        name: "Code Review",
        icon: "🔍",
        description: "Code quality, bug, security, and best practices inspection",
        systemPrompt:
            "You are a senior code reviewer. Focus on: bugs, security vulnerabilities, " +
            "performance, readability, and adherence to best practices. " +
            "Use a structured format: 🔴 Critical / 🟡 Warning / 🟢 Suggestion.",
        allowedTools: ["Read", "Glob", "Grep"],
    },
    {
        id: "test-runner",
        name: "Test Runner",
        icon: "🧪",
        description: "Run test suite and summarize results",
        systemPrompt:
            "Run the project's test suite and provide a concise summary: total / passed / failed. " +
            "For each failing test, show the error and suggest a fix.",
        allowedTools: ["Read", "Bash", "Glob", "Grep"],
    },
    {
        id: "dependency-audit",
        name: "Dependency Audit",
        icon: "📦",
        description: "Check for outdated packages and vulnerabilities, suggest updates",
        systemPrompt:
            "Audit all project dependencies. Check for outdated packages and known vulnerabilities. " +
            "Present results in a table and suggest specific update commands.",
        allowedTools: ["Read", "Bash", "Glob"],
    },
    {
        id: "git-summary",
        name: "Git Summary",
        icon: "📋",
        description: "Summarize recent commits and changes",
        systemPrompt:
            "Summarise recent git history and staged changes in plain Korean. " +
            "Highlight the most important changes and any potential issues.",
        allowedTools: ["Read", "Bash"],
    },
    {
        id: "doc-writer",
        name: "Doc Writer",
        icon: "📝",
        description: "Auto-generate README, API docs, and comments",
        systemPrompt:
            "You are a technical writer. Generate clear, concise documentation in Korean (or English if the codebase is English). " +
            "Follow existing documentation style when present.",
        allowedTools: ["Read", "Write", "Edit", "Glob", "Grep"],
    },
];

// ---------------------------------------------------------------------------
// Lookup helpers
// ---------------------------------------------------------------------------

const skillMap = new Map<string, Skill>(
    DEFAULT_SKILLS.map((s) => [s.id, s]),
);

export function getSkill(id: string): Skill | undefined {
    return skillMap.get(id);
}

export function getAllSkills(): Skill[] {
    return DEFAULT_SKILLS;
}
