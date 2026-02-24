// Bridge config: re-exports constants that shared modules import from "./config.js"
export {
  SESSION_DIR,
  IMAGE_EXTENSIONS,
  SKIP_DIRS,
  SAFE_SYSTEM_COMMANDS,
  SCREENSHOT_KEYWORDS,
  IMAGE_SCAN_TIMEOUT_MS,
  MAX_IMAGES_PER_RESPONSE,
  COMMAND_TIMEOUT_MS,
} from "../config.js";
