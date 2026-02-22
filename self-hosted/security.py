
import os
import re
import threading
import logging
from typing import Set, List, Dict, Any

from config import WORK_DIR, SAFE_SYSTEM_COMMANDS

logger = logging.getLogger(__name__)

# =============================================================================
# Security system: Trusted paths & pending approvals
# =============================================================================

# Trusted paths (whitelist)
TRUSTED_PATHS: Set[str] = {WORK_DIR}  # Default working directory is trusted

# Pending approval tasks (task_id -> task_info)
pending_tasks: Dict[str, Dict[str, Any]] = {}

# Lock for thread safety
trusted_paths_lock = threading.Lock()
pending_tasks_lock = threading.Lock()


def normalize_path(path: str) -> str:
    """Normalize path"""
    return os.path.normpath(os.path.abspath(os.path.expanduser(path)))


def is_path_trusted(path: str) -> bool:
    """Check if a path is trusted"""
    normalized = normalize_path(path)
    with trusted_paths_lock:
        for trusted in TRUSTED_PATHS:
            trusted_norm = normalize_path(trusted)
            # If it's a trusted path or a subdirectory of one
            if normalized == trusted_norm or normalized.startswith(trusted_norm + os.sep):
                return True
    return False


def add_trusted_path(path: str) -> None:
    """Add a trusted path"""
    normalized = normalize_path(path)
    with trusted_paths_lock:
        TRUSTED_PATHS.add(normalized)
        logger.info(f"🔓 Trusted path added: {normalized}")


def remove_trusted_path(path: str) -> bool:
    """Remove a trusted path"""
    normalized = normalize_path(path)
    with trusted_paths_lock:
        if normalized in TRUSTED_PATHS and normalized != normalize_path(WORK_DIR):
            TRUSTED_PATHS.remove(normalized)
            logger.info(f"🔒 Trusted path removed: {normalized}")
            return True
    return False


def get_trusted_paths() -> List[str]:
    """Return list of trusted paths"""
    with trusted_paths_lock:
        return sorted(list(TRUSTED_PATHS))


def extract_paths_from_message(message: str) -> List[str]:
    """Extract paths from message"""
    paths = []

    # Absolute path pattern (starts with /)
    abs_pattern = r'(/[a-zA-Z0-9_\-./]+)'
    abs_matches = re.findall(abs_pattern, message)
    paths.extend(abs_matches)

    # Relative path pattern (starts with ./ or ../)
    rel_pattern = r'(\.\./[a-zA-Z0-9_\-./]+|\.\/[a-zA-Z0-9_\-./]+)'
    rel_matches = re.findall(rel_pattern, message)
    paths.extend(rel_matches)

    # Pattern with file extensions
    file_pattern = r'([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)'
    file_matches = re.findall(file_pattern, message)
    paths.extend(file_matches)

    # Deduplicate and normalize
    unique_paths = []
    seen = set()
    for p in paths:
        # Exclude extension-only strings (e.g. .png)
        if p.startswith('.') and '/' not in p:
            continue
        normalized = normalize_path(p) if p.startswith('/') else p
        if normalized not in seen:
            seen.add(normalized)
            unique_paths.append(p)

    return unique_paths


def check_untrusted_paths(message: str) -> List[str]:
    """Find untrusted paths in a message"""
    paths = extract_paths_from_message(message)
    untrusted = []

    for path in paths:
        # Only check absolute paths
        if path.startswith('/'):
            if not is_path_trusted(path):
                untrusted.append(path)

    return untrusted


def is_safe_system_command(message: str) -> bool:
    """Check if it's a safe system command"""
    msg_lower = message.lower().strip()
    for cmd in SAFE_SYSTEM_COMMANDS:
        if cmd in msg_lower:
            return True
    return False
