import {
  readdirSync,
  statSync,
  readFileSync,
} from "node:fs";
import path from "node:path";
import { IMAGE_EXTENSIONS, SKIP_DIRS } from "./config.js";

export interface ImageMtimeMap {
  [filePath: string]: number; // mtime in ms
}

/**
 * Recursively scan directory for images and their modification times.
 */
export function getImagesWithMtime(
  workDir: string,
  maxDepth = 2,
): ImageMtimeMap {
  const result: ImageMtimeMap = {};

  function scan(dir: string, depth: number): void {
    if (depth > maxDepth) return;
    try {
      const entries = readdirSync(dir, { withFileTypes: true });
      for (const entry of entries) {
        if (SKIP_DIRS.has(entry.name)) continue;

        const fullPath = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          scan(fullPath, depth + 1);
        } else if (entry.isFile()) {
          const ext = path.extname(entry.name).toLowerCase();
          if (IMAGE_EXTENSIONS.has(ext)) {
            try {
              const stat = statSync(fullPath);
              result[fullPath] = stat.mtimeMs;
            } catch {
              // skip inaccessible files
            }
          }
        }
      }
    } catch {
      // skip inaccessible directories
    }
  }

  scan(workDir, 0);
  return result;
}

/**
 * Find images that are new or modified since the before snapshot.
 */
export function findNewOrModifiedImages(
  workDir: string,
  before: ImageMtimeMap,
): string[] {
  const after = getImagesWithMtime(workDir);
  const newImages: string[] = [];

  for (const [filePath, mtime] of Object.entries(after)) {
    if (!(filePath in before) || mtime > before[filePath]) {
      newImages.push(filePath);
    }
  }

  return newImages;
}

/**
 * Convert an image file to base64 string.
 */
export function imageToBase64(imagePath: string): string | null {
  try {
    const buffer = readFileSync(imagePath);
    return buffer.toString("base64");
  } catch {
    return null;
  }
}

/**
 * Extract image file paths mentioned in text (e.g., Claude's response).
 */
export function extractImagePathsFromText(
  text: string,
  workDir: string,
): string[] {
  const paths: string[] = [];
  const seen = new Set<string>();

  // Match absolute paths with image extensions
  const absPathRe = /(\/[^\s:*?"<>|]+\.(?:png|jpg|jpeg|gif|webp|bmp))/gi;
  let match: RegExpExecArray | null;
  while ((match = absPathRe.exec(text)) !== null) {
    const p = match[1];
    if (!seen.has(p)) {
      seen.add(p);
      paths.push(p);
    }
  }

  // Match filenames (search in workDir)
  const filenameRe = /\b([\w.-]+\.(?:png|jpg|jpeg|gif|webp|bmp))\b/gi;
  while ((match = filenameRe.exec(text)) !== null) {
    const filename = match[1];
    const fullPath = path.join(workDir, filename);
    if (!seen.has(fullPath)) {
      try {
        statSync(fullPath);
        seen.add(fullPath);
        paths.push(fullPath);
      } catch {
        // file doesn't exist in workDir, skip
      }
    }
  }

  return paths;
}
