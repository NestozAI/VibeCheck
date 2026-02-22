import { existsSync, readFileSync, readdirSync } from "node:fs";
import { execSync, spawn, type ChildProcess } from "node:child_process";
import path from "node:path";
import os from "node:os";
import net from "node:net";

export interface ProjectInfo {
  type: "static" | "node" | "python" | "unknown";
  framework: string | null;
  cmd?: string;
  entry?: string;
  port?: number;
}

/**
 * Detect project type from directory contents.
 */
export function detectProjectType(projectDir: string): ProjectInfo {
  // Check package.json for Node.js projects
  const pkgPath = path.join(projectDir, "package.json");
  if (existsSync(pkgPath)) {
    try {
      const pkg = JSON.parse(readFileSync(pkgPath, "utf-8"));
      const deps = {
        ...pkg.dependencies,
        ...pkg.devDependencies,
      };

      if (deps["next"]) {
        return {
          type: "node",
          framework: "Next.js",
          cmd: "npx next dev",
          port: 3000,
        };
      }
      if (deps["vite"]) {
        return {
          type: "node",
          framework: "Vite",
          cmd: "npx vite",
          port: 5173,
        };
      }
      if (deps["react-scripts"]) {
        return {
          type: "node",
          framework: "Create React App",
          cmd: "npx react-scripts start",
          port: 3000,
        };
      }
      if (deps["@vue/cli-service"]) {
        return {
          type: "node",
          framework: "Vue CLI",
          cmd: "npx vue-cli-service serve",
          port: 8080,
        };
      }
      // Generic Node.js with start script
      if (pkg.scripts?.dev) {
        return {
          type: "node",
          framework: "Node.js",
          cmd: "npm run dev",
          port: 3000,
        };
      }
      if (pkg.scripts?.start) {
        return {
          type: "node",
          framework: "Node.js",
          cmd: "npm start",
          port: 3000,
        };
      }
    } catch {
      // ignore parse errors
    }
  }

  // Check for Python projects
  const requirementsPath = path.join(projectDir, "requirements.txt");
  const pyprojectPath = path.join(projectDir, "pyproject.toml");
  if (existsSync(requirementsPath) || existsSync(pyprojectPath)) {
    // Check for Streamlit
    for (const name of [
      "app.py",
      "main.py",
      "streamlit_app.py",
    ]) {
      const fp = path.join(projectDir, name);
      if (existsSync(fp)) {
        try {
          const content = readFileSync(fp, "utf-8");
          if (content.includes("streamlit")) {
            return {
              type: "python",
              framework: "Streamlit",
              cmd: `streamlit run ${name}`,
              entry: name,
              port: 8501,
            };
          }
        } catch {
          // ignore
        }
      }
    }

    // Check for FastAPI
    const mainPy = path.join(projectDir, "main.py");
    if (existsSync(mainPy)) {
      try {
        const content = readFileSync(mainPy, "utf-8");
        if (content.includes("fastapi") || content.includes("FastAPI")) {
          return {
            type: "python",
            framework: "FastAPI",
            cmd: "uvicorn main:app --reload",
            entry: "main.py",
            port: 8000,
          };
        }
      } catch {
        // ignore
      }
    }

    // Check for Flask
    const appPy = path.join(projectDir, "app.py");
    if (existsSync(appPy)) {
      try {
        const content = readFileSync(appPy, "utf-8");
        if (content.includes("flask") || content.includes("Flask")) {
          return {
            type: "python",
            framework: "Flask",
            cmd: "flask run",
            entry: "app.py",
            port: 5000,
          };
        }
      } catch {
        // ignore
      }
    }
  }

  // Check for static HTML
  const indexHtml = path.join(projectDir, "index.html");
  if (existsSync(indexHtml)) {
    return {
      type: "static",
      framework: null,
      entry: "index.html",
    };
  }

  // Look for any HTML file
  try {
    const files = readdirSync(projectDir);
    const htmlFile = files.find((f) => f.endsWith(".html"));
    if (htmlFile) {
      return {
        type: "static",
        framework: null,
        entry: htmlFile,
      };
    }
  } catch {
    // ignore
  }

  return { type: "unknown", framework: null };
}

/**
 * Wait for a port to become available.
 */
function waitForPort(
  port: number,
  timeoutMs: number,
): Promise<boolean> {
  return new Promise((resolve) => {
    const start = Date.now();
    const check = () => {
      const socket = new net.Socket();
      socket.setTimeout(500);
      socket.once("connect", () => {
        socket.destroy();
        resolve(true);
      });
      socket.once("error", () => {
        socket.destroy();
        if (Date.now() - start > timeoutMs) {
          resolve(false);
        } else {
          setTimeout(check, 500);
        }
      });
      socket.once("timeout", () => {
        socket.destroy();
        if (Date.now() - start > timeoutMs) {
          resolve(false);
        } else {
          setTimeout(check, 500);
        }
      });
      socket.connect(port, "127.0.0.1");
    };
    check();
  });
}

/**
 * Take a screenshot of an HTML file using Playwright.
 */
export async function htmlFileToScreenshot(
  htmlPath: string,
  outputPath: string,
): Promise<string | null> {
  try {
    const { chromium } = await import("playwright");
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({
      viewport: { width: 1200, height: 800 },
    });
    await page.goto(`file://${path.resolve(htmlPath)}`);
    await page.waitForTimeout(500);
    await page.screenshot({ path: outputPath, fullPage: true });
    await browser.close();
    return outputPath;
  } catch (e) {
    console.error("[screenshot] HTML 스크린샷 실패:", e);
    return null;
  }
}

/**
 * Take a screenshot of a project by starting its dev server.
 */
export async function screenshotProject(
  projectDir: string,
  outputPath: string,
): Promise<string | null> {
  const info = detectProjectType(projectDir);

  // Static HTML: screenshot directly
  if (info.type === "static" && info.entry) {
    const htmlPath = path.join(projectDir, info.entry);
    return htmlFileToScreenshot(htmlPath, outputPath);
  }

  // Dev server projects: start server, screenshot, kill
  if (!info.cmd || !info.port) {
    return null;
  }

  let serverProcess: ChildProcess | null = null;

  try {
    // Ensure npm dependencies are installed for Node.js projects
    if (
      info.type === "node" &&
      !existsSync(path.join(projectDir, "node_modules"))
    ) {
      console.log("[screenshot] npm install 실행 중...");
      execSync("npm install", {
        cwd: projectDir,
        timeout: 60_000,
        stdio: "ignore",
      });
    }

    // Start dev server
    const [cmd, ...args] = info.cmd.split(" ");
    serverProcess = spawn(cmd, args, {
      cwd: projectDir,
      stdio: "ignore",
      detached: true,
      env: { ...process.env, PORT: String(info.port), BROWSER: "none" },
    });

    // Wait for port to open
    const portReady = await waitForPort(info.port, 30_000);
    if (!portReady) {
      console.warn("[screenshot] 서버 시작 타임아웃 (30초)");
      return null;
    }

    // Take screenshot
    try {
      const { chromium } = await import("playwright");
      const browser = await chromium.launch({ headless: true });
      const page = await browser.newPage({
        viewport: { width: 1200, height: 800 },
      });
      await page.goto(`http://localhost:${info.port}`, {
        waitUntil: "networkidle",
        timeout: 15_000,
      });
      await page.screenshot({ path: outputPath, fullPage: true });
      await browser.close();
      return outputPath;
    } catch (e) {
      console.error("[screenshot] 스크린샷 캡처 실패:", e);
      return null;
    }
  } catch (e) {
    console.error("[screenshot] 프로젝트 스크린샷 실패:", e);
    return null;
  } finally {
    // Kill dev server process group
    if (serverProcess && serverProcess.pid) {
      try {
        process.kill(-serverProcess.pid, "SIGTERM");
      } catch {
        try {
          serverProcess.kill("SIGKILL");
        } catch {
          // ignore
        }
      }
    }
  }
}

/**
 * Find the project directory from a message or response text.
 * Looks for paths that contain typical project indicators.
 */
export function findProjectDir(
  text: string,
  workDir: string,
): string | null {
  // Check if workDir itself is a project
  const info = detectProjectType(workDir);
  if (info.type !== "unknown") {
    return workDir;
  }

  // Look for directory paths in the text
  const dirRe = /(\/[^\s:*?"<>|]+)/g;
  let match: RegExpExecArray | null;
  while ((match = dirRe.exec(text)) !== null) {
    const dir = match[1];
    try {
      const projInfo = detectProjectType(dir);
      if (projInfo.type !== "unknown") {
        return dir;
      }
    } catch {
      // not a valid directory
    }
  }

  // Check subdirectories of workDir (1 level deep)
  try {
    const entries = readdirSync(workDir, { withFileTypes: true });
    for (const entry of entries) {
      if (
        entry.isDirectory() &&
        !entry.name.startsWith(".") &&
        entry.name !== "node_modules"
      ) {
        const subDir = path.join(workDir, entry.name);
        const subInfo = detectProjectType(subDir);
        if (subInfo.type !== "unknown") {
          return subDir;
        }
      }
    }
  } catch {
    // ignore
  }

  return null;
}

/**
 * Get screenshot output path.
 */
export function getScreenshotPath(): string {
  return path.join(os.tmpdir(), "vibecheck_screenshot.png");
}
