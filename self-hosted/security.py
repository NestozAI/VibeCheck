
import os
import re
import threading
import logging
from typing import Set, List, Dict, Any

from config import WORK_DIR, SAFE_SYSTEM_COMMANDS

logger = logging.getLogger(__name__)

# =============================================================================
# 🛡️ 보안 시스템: 신뢰 경로 & 승인 대기
# =============================================================================

# 신뢰할 수 있는 경로 (화이트리스트)
TRUSTED_PATHS: Set[str] = {WORK_DIR}  # 기본 작업 디렉토리는 신뢰

# 승인 대기 중인 작업들 (task_id -> task_info)
pending_tasks: Dict[str, Dict[str, Any]] = {}

# Lock for thread safety
trusted_paths_lock = threading.Lock()
pending_tasks_lock = threading.Lock()


def normalize_path(path: str) -> str:
    """경로 정규화"""
    return os.path.normpath(os.path.abspath(os.path.expanduser(path)))


def is_path_trusted(path: str) -> bool:
    """경로가 신뢰할 수 있는지 확인"""
    normalized = normalize_path(path)
    with trusted_paths_lock:
        for trusted in TRUSTED_PATHS:
            trusted_norm = normalize_path(trusted)
            # 신뢰 경로 또는 그 하위 경로인 경우
            if normalized == trusted_norm or normalized.startswith(trusted_norm + os.sep):
                return True
    return False


def add_trusted_path(path: str) -> None:
    """신뢰 경로 추가"""
    normalized = normalize_path(path)
    with trusted_paths_lock:
        TRUSTED_PATHS.add(normalized)
        logger.info(f"🔓 신뢰 경로 추가: {normalized}")


def remove_trusted_path(path: str) -> bool:
    """신뢰 경로 제거"""
    normalized = normalize_path(path)
    with trusted_paths_lock:
        if normalized in TRUSTED_PATHS and normalized != normalize_path(WORK_DIR):
            TRUSTED_PATHS.remove(normalized)
            logger.info(f"🔒 신뢰 경로 제거: {normalized}")
            return True
    return False


def get_trusted_paths() -> List[str]:
    """신뢰 경로 목록 반환"""
    with trusted_paths_lock:
        return sorted(list(TRUSTED_PATHS))


def extract_paths_from_message(message: str) -> List[str]:
    """메시지에서 경로 추출"""
    paths = []

    # 절대 경로 패턴 (/로 시작)
    abs_pattern = r'(/[a-zA-Z0-9_\-./]+)'
    abs_matches = re.findall(abs_pattern, message)
    paths.extend(abs_matches)

    # 상대 경로 패턴 (./나 ../ 로 시작)
    rel_pattern = r'(\.\./[a-zA-Z0-9_\-./]+|\.\/[a-zA-Z0-9_\-./]+)'
    rel_matches = re.findall(rel_pattern, message)
    paths.extend(rel_matches)

    # 파일 확장자가 있는 패턴
    file_pattern = r'([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)'
    file_matches = re.findall(file_pattern, message)
    paths.extend(file_matches)

    # 중복 제거 및 정규화
    unique_paths = []
    seen = set()
    for p in paths:
        # 확장자만 있는 것 제외 (예: .png)
        if p.startswith('.') and '/' not in p:
            continue
        normalized = normalize_path(p) if p.startswith('/') else p
        if normalized not in seen:
            seen.add(normalized)
            unique_paths.append(p)

    return unique_paths


def check_untrusted_paths(message: str) -> List[str]:
    """메시지에서 신뢰되지 않은 경로 찾기"""
    paths = extract_paths_from_message(message)
    untrusted = []

    for path in paths:
        # 절대 경로만 검사
        if path.startswith('/'):
            if not is_path_trusted(path):
                untrusted.append(path)

    return untrusted


def is_safe_system_command(message: str) -> bool:
    """안전한 시스템 명령어인지 확인"""
    msg_lower = message.lower().strip()
    for cmd in SAFE_SYSTEM_COMMANDS:
        if cmd in msg_lower:
            return True
    return False
