/**
 * Output Cleaner
 * - ANSI escape code removal
 * - Noise filtering (spinners, progress indicators)
 * - Code block normalization
 * - Message splitting for Slack
 */

const ANSI_REGEX = new RegExp(
  [
    "\\x1b\\[[0-9;]*[a-zA-Z]",
    "\\x1b\\][^\\x07]*\\x07",
    "\\x1b\\[\\?[0-9;]*[a-zA-Z]",
    "\\x1b[PX^_][^\\x1b]*\\x1b\\\\",
    "\\x1b\\([A-Z0-9]",
    "\\x1b[=>]",
    "\\x1b[78]",
    "\\x1b[DEFGHJKLMOPQRSTUVWXYZ]",
    "\\r",
    "\\x07",
  ].join("|"),
  "g"
);

const SPINNER_CHARS = new Set(
  "/\\|─━-⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏●○◐◑◒◓".split("")
);

const NOISE_PATTERNS = [
  /^[\s]*[/\\|─━\-⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏●○◐◑◒◓][\s]*$/,
  /^[\s]*(loading|processing|thinking|waiting|connecting|initializing)\.{0,3}[\s]*$/i,
  /^[\s]*$/,
  /^\s*\d+;\d+[HR]/,
  /[[\u2588\u2593\u2592\u2591\]]{3,}/,
  /\d+%\s*[[\u2588\u2593\u2592\u2591\]]*/,
  /^[\s]*›[\s]*$/,
  /^[\s]*\.\.\.$/,
  /^\s*⠋\s*/,
  /^\s*⠙\s*/,
  /^\s*⠹\s*/,
  /^\.+$/,
];

export function removeAnsi(text: string): string {
  return text.replace(ANSI_REGEX, "");
}

function isNoiseLine(line: string): boolean {
  const cleaned = line.trim();
  if (!cleaned) return true;

  if ([...cleaned].every((c) => SPINNER_CHARS.has(c) || c === " ")) {
    return true;
  }

  for (const pattern of NOISE_PATTERNS) {
    if (pattern.test(cleaned)) return true;
  }

  return false;
}

export function filterNoise(text: string): string {
  const lines = text.split("\n");
  const filtered = lines.filter((line) => !isNoiseLine(line));

  const result: string[] = [];
  let prevEmpty = false;
  for (const line of filtered) {
    const isEmpty = !line.trim();
    if (isEmpty) {
      if (!prevEmpty) result.push(line);
      prevEmpty = true;
    } else {
      result.push(line);
      prevEmpty = false;
    }
  }

  return result.join("\n");
}

export function fixCodeBlocks(text: string): string {
  return text.replace(/```(\w*)\n?(.*?)```/gs, (_match, lang, code) => {
    return `\`\`\`${lang}\n${(code as string).trim()}\n\`\`\``;
  });
}

const SLACK_MAX_LENGTH = 3900;

export function splitMessage(
  text: string,
  maxLength = SLACK_MAX_LENGTH
): string[] {
  if (text.length <= maxLength) return [text];

  const chunks: string[] = [];
  let current = "";
  let inCodeBlock = false;
  let codeBlockLang = "";

  for (const line of text.split("\n")) {
    if (line.trim().startsWith("```")) {
      if (!inCodeBlock) {
        inCodeBlock = true;
        codeBlockLang = line.trim().slice(3);
      } else {
        inCodeBlock = false;
        codeBlockLang = "";
      }
    }

    const test = current + line + "\n";
    if (test.length > maxLength) {
      if (inCodeBlock && current) {
        current += "```\n";
        chunks.push(current.trim());
        current = `\`\`\`${codeBlockLang}\n${line}\n`;
      } else {
        chunks.push(current.trim());
        current = line + "\n";
      }
    } else {
      current = test;
    }
  }

  if (current.trim()) chunks.push(current.trim());
  return chunks;
}

export function cleanOutput(rawText: string): string | null {
  if (!rawText) return null;

  let text = removeAnsi(rawText);
  text = filterNoise(text);
  text = fixCodeBlocks(text);
  text = text.trim();

  return text.length > 0 ? text : null;
}

export function cleanAndSplit(rawText: string): string[] {
  const cleaned = cleanOutput(rawText);
  if (!cleaned) return [];
  return splitMessage(cleaned);
}
