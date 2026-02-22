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
        name: "리서치 에이전트",
        icon: "🔭",
        description: "읽기 전용 — 코드 분석, 문서 검색, 정보 수집에 최적화",
        systemPrompt:
            "You are a research agent. You ONLY read and analyse — never modify files. " +
            "Provide detailed, well-structured summaries and insights.",
        allowedTools: ["Read", "Glob", "Grep", "WebFetch", "WebSearch"],
    },
    {
        id: "coding",
        name: "코딩 에이전트",
        icon: "💻",
        description: "파일 수정 가능 — 코딩, 리팩터링, 버그 수정에 최적화",
        systemPrompt:
            "You are an expert software engineer. Write clean, well-tested, idiomatic code. " +
            "Explain every change you make.",
        // No allowedTools restriction — uses the global list
    },

    // ── Quick-action skills ───────────────────────────────────────────────────

    {
        id: "code-review",
        name: "코드 리뷰",
        icon: "🔍",
        description: "코드 품질, 버그, 보안 이슈, 모범 사례 점검",
        systemPrompt:
            "You are a senior code reviewer. Focus on: bugs, security vulnerabilities, " +
            "performance, readability, and adherence to best practices. " +
            "Use a structured format: 🔴 Critical / 🟡 Warning / 🟢 Suggestion.",
        allowedTools: ["Read", "Glob", "Grep"],
    },
    {
        id: "test-runner",
        name: "테스트 실행",
        icon: "🧪",
        description: "테스트 스위트 실행 후 결과 요약",
        systemPrompt:
            "Run the project's test suite and provide a concise summary: total / passed / failed. " +
            "For each failing test, show the error and suggest a fix.",
        allowedTools: ["Read", "Bash", "Glob", "Grep"],
    },
    {
        id: "dependency-audit",
        name: "의존성 감사",
        icon: "📦",
        description: "오래된 패키지·취약점 확인 및 업데이트 제안",
        systemPrompt:
            "Audit all project dependencies. Check for outdated packages and known vulnerabilities. " +
            "Present results in a table and suggest specific update commands.",
        allowedTools: ["Read", "Bash", "Glob"],
    },
    {
        id: "git-summary",
        name: "Git 요약",
        icon: "📋",
        description: "최근 커밋 및 변경 사항 요약",
        systemPrompt:
            "Summarise recent git history and staged changes in plain Korean. " +
            "Highlight the most important changes and any potential issues.",
        allowedTools: ["Read", "Bash"],
    },
    {
        id: "doc-writer",
        name: "문서 작성",
        icon: "📝",
        description: "README, API 문서, 주석 자동 작성",
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
