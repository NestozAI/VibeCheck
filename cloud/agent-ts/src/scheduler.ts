import * as cron from "node-cron";
import {
    existsSync,
    mkdirSync,
    readFileSync,
    writeFileSync,
} from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { SESSION_DIR } from "./config.js";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ScheduledTask {
    id: string;
    cron: string;       // standard 5-field cron expression
    message: string;    // prompt to send to Claude
    skill_id?: string;  // optional skill preset
    enabled: boolean;
    created_at: string;
    last_run?: string;
    last_result?: string;
}

// ---------------------------------------------------------------------------
// Persistence
// ---------------------------------------------------------------------------

const SCHEDULE_FILE = path.join(SESSION_DIR, "schedules.json");

function loadTasks(): ScheduledTask[] {
    try {
        if (!existsSync(SCHEDULE_FILE)) return [];
        return JSON.parse(readFileSync(SCHEDULE_FILE, "utf-8")) as ScheduledTask[];
    } catch {
        return [];
    }
}

function saveTasks(tasks: ScheduledTask[]): void {
    try {
        if (!existsSync(SESSION_DIR)) mkdirSync(SESSION_DIR, { recursive: true });
        writeFileSync(SCHEDULE_FILE, JSON.stringify(tasks, null, 2));
    } catch (e) {
        console.error("[scheduler] 태스크 저장 실패:", e);
    }
}

// ---------------------------------------------------------------------------
// Scheduler
// ---------------------------------------------------------------------------

export class TaskScheduler {
    private tasks: ScheduledTask[] = [];
    private cronJobs = new Map<string, cron.ScheduledTask>();

    /**
     * Called when a scheduled task fires.
     * agent.ts wires this to claude.execute() + WebSocket response.
     */
    onTaskFire?: (task: ScheduledTask) => Promise<void>;

    constructor() {
        this.tasks = loadTasks();
    }

    /** Start all enabled tasks (call once at agent startup) */
    start(): void {
        for (const task of this.tasks) {
            if (task.enabled) this.scheduleJob(task);
        }
        console.log(
            `[scheduler] ${this.tasks.filter((t) => t.enabled).length}개 태스크 활성화`,
        );
    }

    /** Stop all cron jobs (call on shutdown) */
    stop(): void {
        for (const job of this.cronJobs.values()) job.stop();
        this.cronJobs.clear();
    }

    // ── CRUD ──────────────────────────────────────────────────────────────────

    addTask(
        cronExpr: string,
        message: string,
        skillId?: string,
    ): ScheduledTask | { error: string } {
        if (!cron.validate(cronExpr)) {
            return { error: `유효하지 않은 cron 표현식: "${cronExpr}"` };
        }

        const task: ScheduledTask = {
            id: randomUUID(),
            cron: cronExpr,
            message,
            skill_id: skillId,
            enabled: true,
            created_at: new Date().toISOString(),
        };

        this.tasks.push(task);
        saveTasks(this.tasks);
        this.scheduleJob(task);

        console.log(`[scheduler] 태스크 추가: ${task.id.slice(0, 8)} "${message.slice(0, 40)}"`);
        return task;
    }

    removeTask(id: string): boolean {
        const idx = this.tasks.findIndex((t) => t.id === id);
        if (idx === -1) return false;

        this.cronJobs.get(id)?.stop();
        this.cronJobs.delete(id);
        this.tasks.splice(idx, 1);
        saveTasks(this.tasks);
        console.log(`[scheduler] 태스크 삭제: ${id.slice(0, 8)}`);
        return true;
    }

    toggleTask(id: string, enabled: boolean): boolean {
        const task = this.tasks.find((t) => t.id === id);
        if (!task) return false;

        task.enabled = enabled;
        if (enabled) {
            this.scheduleJob(task);
        } else {
            this.cronJobs.get(id)?.stop();
            this.cronJobs.delete(id);
        }
        saveTasks(this.tasks);
        return true;
    }

    getAll(): ScheduledTask[] {
        return this.tasks;
    }

    // ── Internal ──────────────────────────────────────────────────────────────

    private scheduleJob(task: ScheduledTask): void {
        // Stop existing job if any
        this.cronJobs.get(task.id)?.stop();

        const job = cron.schedule(task.cron, async () => {
            console.log(`[scheduler] 태스크 실행: "${task.message.slice(0, 40)}"`);
            task.last_run = new Date().toISOString();
            saveTasks(this.tasks);

            try {
                await this.onTaskFire?.(task);
            } catch (e) {
                console.error("[scheduler] 태스크 실행 오류:", e);
            }
        });

        this.cronJobs.set(task.id, job);
    }

    /** Update last_result after a task fires */
    recordResult(taskId: string, result: string): void {
        const task = this.tasks.find((t) => t.id === taskId);
        if (task) {
            task.last_result = result.slice(0, 200);
            saveTasks(this.tasks);
        }
    }
}
