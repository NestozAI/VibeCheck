#!/usr/bin/env node
/**
 * Effect 스캐너 — effects.manifest.json 기반 (GOVERNANCE.md Layer 1–3)
 *
 * 탐지 축: import + 클라이언트 생성자. `.set(`/`fetch(` 류 메서드명 grep은
 * 오탐(정규식 .exec(), searchParams.set 등) 때문에 금지 — 이 리포에서 실측으로
 * 확인된 교훈이다 (RegExp.exec() 히트 다수).
 *
 * 판정:
 *   ✓ 등록          — 어떤 effect의 exit_patterns와 매칭 && 그 effect의 allowed_sites 안
 *   ✗ BOUNDARY      — 패턴은 effect에 등록돼 있으나 allowed_sites 밖 파일
 *   ✗ UNREGISTERED  — 어떤 effect에도 매칭 안 되는 출구 (미지의 효과)
 *   • STALE         — 매니페스트에 있으나 코드 히트 0 (죽은 등록)
 *   • MANUAL        — 스캐너가 검증하지 못하는 recon 항목 (숨기지 않고 출력)
 *
 * 위반 시 exit 1. 사용법: node scripts/scan-effects.mjs
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const manifest = JSON.parse(
  readFileSync(path.join(ROOT, "effects.manifest.json"), "utf8"),
);

// ── 기본 패턴 (§1 분류표의 TS/Node 번역 — import/생성자 축) ────────────────
// 오탐을 줄이려고 여기서 패턴을 지우지 말 것 — 놓침이 오탐보다 비싸다.
const BASE_PATTERNS = [
  // network
  'from "ws"',
  "new WebSocket\\(",
  "new WebSocketServer",
  "fetch\\(",
  "axios",
  'from "node:https"',
  'from "node:http"',
  'from "node:net"',
  // sdk
  "@anthropic-ai/claude-agent-sdk",
  "@slack/bolt",
  "new App\\(",
  '"stripe"',
  "@aws-sdk/",
  "firebase-admin",
  "playwright",
  "chromium\\.launch",
  // process
  'from "node:child_process"',
  '"child_process"',
  "systemctl (restart|stop|start)",
];

// filesystem write는 import 조건부 2단 탐지: node:fs를 import한 파일에서만
// write 계열 호출명을 본다 (임의 파일의 .write( 메서드명 grep이 아님)
const FS_IMPORT_RE = /from\s+["']node:fs["']|require\(["']fs["']\)/;
const FS_WRITE_RE =
  /\b(writeFileSync|appendFileSync|mkdirSync|rmSync|unlinkSync|createWriteStream|writeFile\()/;
const FS_PSEUDO = "__fs_write__";

const allPatterns = [
  ...new Set([
    ...BASE_PATTERNS,
    ...manifest.effects.flatMap((e) => e.exit_patterns),
  ]),
].filter((p) => p !== FS_PSEUDO);
const compiled = allPatterns.map((p) => ({ src: p, re: new RegExp(p) }));

// ── 소스 수집 ──────────────────────────────────────────────────────────────
const SKIP_DIRS = new Set(["node_modules", "dist", "__pycache__", ".git"]);
const EXTS = new Set([".ts", ".mjs", ".sh"]);

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue;
    const full = path.join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) yield* walk(full);
    else if (EXTS.has(path.extname(name)) && !name.endsWith(".d.ts")) yield full;
  }
}

const files = manifest.sources.flatMap((src) => {
  const dir = path.join(ROOT, src);
  try {
    statSync(dir);
  } catch {
    return [];
  }
  return [...walk(dir)];
});

// ── 판정 ───────────────────────────────────────────────────────────────────
const rel = (f) => path.relative(ROOT, f).replaceAll("\\", "/");

function isExempt(file) {
  return (manifest.exceptions ?? []).some((x) => {
    if (!file.startsWith(x.path) && file !== x.path) return false;
    if (new Date(x.expires) > new Date()) return true;
    console.log(`✗ EXPIRED exception: ${file} (expires ${x.expires}) — 갱신 또는 정식 등록 필요`);
    violations++;
    return true; // 이중 보고 방지 (위반은 이미 집계됨)
  });
}

function isCommentLine(line, ext) {
  const t = line.trim();
  if (ext === ".sh") return t.startsWith("#");
  return t.startsWith("//") || t.startsWith("*") || t.startsWith("/*");
}

let violations = 0;
const hitCount = new Map(manifest.effects.map((e) => [e.id, 0]));

for (const file of files) {
  const relPath = rel(file);
  if (isExempt(relPath)) continue;
  const ext = path.extname(file);
  const lines = readFileSync(file, "utf8").split("\n");
  const importsFs = FS_IMPORT_RE.test(lines.join("\n"));

  lines.forEach((line, i) => {
    if (isCommentLine(line, ext)) return;
    if (/^\s*import\s+type\s/.test(line)) return; // 타입 전용 import는 출구가 아님

    const hits = [];
    for (const { src, re } of compiled) if (re.test(line)) hits.push(src);
    if (importsFs && FS_WRITE_RE.test(line)) hits.push(FS_PSEUDO);
    if (hits.length === 0) return;

    // 이 라인을 자기 exit_patterns + allowed_sites로 소유하는 effect가 있는가
    const owner = manifest.effects.find(
      (e) =>
        e.allowed_sites.includes(relPath) &&
        e.exit_patterns.some((p) =>
          p === FS_PSEUDO ? hits.includes(FS_PSEUDO) : new RegExp(p).test(line),
        ),
    );
    if (owner) {
      hitCount.set(owner.id, hitCount.get(owner.id) + 1);
      return;
    }

    // 패턴은 알려져 있으나 허용 위치 밖인가
    const claimed = manifest.effects.find((e) =>
      e.exit_patterns.some((p) =>
        p === FS_PSEUDO ? hits.includes(FS_PSEUDO) : new RegExp(p).test(line),
      ),
    );
    const loc = `${relPath}:${i + 1}`;
    if (claimed) {
      console.log(`✗ BOUNDARY [${claimed.id}] ${loc}  ${line.trim().slice(0, 90)}`);
    } else {
      console.log(`✗ UNREGISTERED ${loc}  (${hits.join(", ")})  ${line.trim().slice(0, 90)}`);
    }
    violations++;
  });
}

// ── STALE + MANUAL 출력 ────────────────────────────────────────────────────
for (const e of manifest.effects) {
  if (hitCount.get(e.id) === 0) console.log(`• STALE: ${e.id} — 코드 히트 0 (죽은 등록?)`);
}
for (const e of manifest.effects) {
  if (/\[manual\]/i.test(e.recon) || /\[manual\]/i.test(e.log_stream)) {
    console.log(`• MANUAL recon 필요: ${e.id} — ${e.recon}`);
  }
}

console.log(
  violations === 0
    ? `\n✓ scan-effects: ${files.length} files, 위반 0`
    : `\n✗ scan-effects: 위반 ${violations}건`,
);
process.exit(violations ? 1 : 0);
