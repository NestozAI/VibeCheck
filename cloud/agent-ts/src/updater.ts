import { execSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);

function getInstalledVersion(): string {
  const pkgPath = path.resolve(
    path.dirname(fileURLToPath(import.meta.url)),
    "..",
    "package.json",
  );
  const pkg = require(pkgPath);
  return pkg.version;
}

function getLatestVersion(): string | null {
  try {
    const result = execSync("npm view vibecheck-agent version", {
      encoding: "utf-8",
      timeout: 10_000,
      stdio: ["pipe", "pipe", "pipe"],
    });
    return result.trim();
  } catch {
    return null;
  }
}

function isNewer(latest: string, current: string): boolean {
  const [lMaj, lMin, lPat] = latest.split(".").map(Number);
  const [cMaj, cMin, cPat] = current.split(".").map(Number);
  if (lMaj !== cMaj) return lMaj > cMaj;
  if (lMin !== cMin) return lMin > cMin;
  return lPat > cPat;
}

export async function checkForUpdates(): Promise<boolean> {
  const current = getInstalledVersion();
  console.log(`[updater] Current version: ${current}`);

  const latest = getLatestVersion();
  if (!latest) {
    console.log("[updater] Could not check for updates, skipping");
    return false;
  }

  if (!isNewer(latest, current)) {
    console.log(`[updater] Already up to date (${current})`);
    return false;
  }

  console.log(`[updater] New version available: ${current} → ${latest}`);
  console.log("[updater] Updating...");

  try {
    execSync("npm install -g vibecheck-agent@latest", {
      encoding: "utf-8",
      timeout: 60_000,
      stdio: "inherit",
    });
    console.log(`[updater] Updated to ${latest}. Restarting...`);
    return true;
  } catch (error) {
    console.error(
      "[updater] Update failed:",
      error instanceof Error ? error.message : error,
    );
    return false;
  }
}
