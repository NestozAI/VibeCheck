"""
터미널 출력 청소기 (Cleaner)
- ANSI 이스케이프 코드 제거
- 노이즈 필터링 (스피너, 진행 표시 등)
- 슬랙용 포맷팅
"""

import re
from typing import Optional

# =============================================================================
# ANSI 이스케이프 코드 제거
# =============================================================================

# ANSI 이스케이프 시퀀스 패턴들
ANSI_PATTERNS = [
    r'\x1b\[[0-9;]*[a-zA-Z]',      # CSI sequences: \x1b[0m, \x1b[1;32m 등
    r'\x1b\][^\x07]*\x07',          # OSC sequences: \x1b]0;title\x07
    r'\x1b\[\?[0-9;]*[a-zA-Z]',     # Private sequences: \x1b[?25h
    r'\x1b[PX^_][^\x1b]*\x1b\\',    # DCS, SOS, PM, APC sequences
    r'\x1b\([A-Z0-9]',              # Character set selection
    r'\x1b[=>]',                     # Keypad modes
    r'\x1b[78]',                     # Save/restore cursor
    r'\x1b[DEFGHJKLMOPQRSTUVWXYZ]', # Single character sequences
    r'\r',                           # Carriage return
    r'\x07',                         # Bell
]

# 합쳐진 패턴 (성능 최적화)
ANSI_REGEX = re.compile('|'.join(ANSI_PATTERNS))


def remove_ansi(text: str) -> str:
    """
    ANSI 이스케이프 코드를 완전히 제거

    터미널 색상, 커서 이동, 스크롤 등 모든 제어 문자 제거
    """
    return ANSI_REGEX.sub('', text)


# =============================================================================
# 노이즈 필터링
# =============================================================================

# 무시할 패턴들 (진행 표시, 스피너, 로딩 메시지 등)
NOISE_PATTERNS = [
    # 스피너 문자
    r'^[\s]*[/\\|─━\-⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏●○◐◑◒◓][\s]*$',
    # 진행 표시 메시지 (case insensitive는 함수에서 처리)
    r'^[\s]*(loading|processing|thinking|waiting|connecting|initializing|Loading|Processing|Thinking|Waiting|Connecting|Initializing)\.{0,3}[\s]*$',
    # 빈 줄 또는 공백만 있는 줄
    r'^[\s]*$',
    # 커서 관련 출력
    r'^\s*\d+;\d+[HR]',
    # 진행률 바
    r'[\[█▓▒░\]]{3,}',
    r'\d+%\s*[\[█▓▒░\]]*',
    # Claude Code 특유의 노이즈
    r'^[\s]*›[\s]*$',
    r'^[\s]*\.\.\.$',
    r'^\s*⠋\s*',
    r'^\s*⠙\s*',
    r'^\s*⠹\s*',
    # 반복되는 점들
    r'^\.+$',
]


def is_noise_line(line: str) -> bool:
    """한 줄이 노이즈인지 판별"""
    cleaned = line.strip()

    # 빈 줄
    if not cleaned:
        return True

    # 스피너 문자만 있는 경우
    spinner_chars = set('/\\|─━-⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏●○◐◑◒◓')
    if all(c in spinner_chars or c.isspace() for c in cleaned):
        return True

    # 노이즈 패턴 매칭
    for pattern in NOISE_PATTERNS:
        if re.match(pattern, cleaned, re.IGNORECASE):
            return True

    return False


def filter_noise(text: str) -> str:
    """
    노이즈 라인 제거

    스피너, 로딩 메시지, 진행 표시 등 불필요한 출력 제거
    """
    lines = text.split('\n')
    filtered_lines = [line for line in lines if not is_noise_line(line)]

    # 연속된 빈 줄 정리 (최대 1개)
    result = []
    prev_empty = False
    for line in filtered_lines:
        is_empty = not line.strip()
        if is_empty:
            if not prev_empty:
                result.append(line)
            prev_empty = True
        else:
            result.append(line)
            prev_empty = False

    return '\n'.join(result)


# =============================================================================
# 코드 블록 처리
# =============================================================================

def fix_code_blocks(text: str) -> str:
    """
    코드 블록 포맷 정리

    - 언어 태그 정규화
    - 중첩된 백틱 처리
    - 슬랙 호환 포맷으로 변환
    """
    # 이미 있는 코드 블록 유지
    # ```language ... ``` 형식 확인

    # 백틱 3개로 시작하는 코드 블록 찾기
    code_block_pattern = r'```(\w*)\n?(.*?)```'

    def format_code_block(match):
        lang = match.group(1) or ''
        code = match.group(2)
        # 슬랙은 언어 하이라이팅을 지원하지 않지만 포맷은 유지
        return f'```{lang}\n{code.strip()}\n```'

    text = re.sub(code_block_pattern, format_code_block, text, flags=re.DOTALL)

    return text


# =============================================================================
# 슬랙 메시지 분할
# =============================================================================

SLACK_MAX_LENGTH = 3900  # 슬랙 메시지 최대 길이 (여유 두고 4000 미만)


def split_message(text: str, max_length: int = SLACK_MAX_LENGTH) -> list[str]:
    """
    긴 메시지를 슬랙 제한에 맞게 분할

    코드 블록이 중간에 잘리지 않도록 주의
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    current_chunk = ""
    in_code_block = False
    code_block_lang = ""

    lines = text.split('\n')

    for line in lines:
        # 코드 블록 시작/끝 감지
        if line.strip().startswith('```'):
            if not in_code_block:
                # 코드 블록 시작
                in_code_block = True
                code_block_lang = line.strip()[3:]
            else:
                # 코드 블록 끝
                in_code_block = False
                code_block_lang = ""

        # 현재 청크에 라인 추가 시 길이 확인
        test_chunk = current_chunk + line + '\n'

        if len(test_chunk) > max_length:
            # 청크 분리 필요
            if in_code_block and current_chunk:
                # 코드 블록 중이면 일단 닫고
                current_chunk += '```\n'
                chunks.append(current_chunk.strip())
                # 새 청크에서 다시 열기
                current_chunk = f'```{code_block_lang}\n{line}\n'
            else:
                chunks.append(current_chunk.strip())
                current_chunk = line + '\n'
        else:
            current_chunk = test_chunk

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


# =============================================================================
# 메인 정제 함수
# =============================================================================

def clean_output(raw_text: str) -> Optional[str]:
    """
    터미널 출력을 슬랙에 보내기 좋게 정제

    1. ANSI 코드 제거
    2. 노이즈 필터링
    3. 코드 블록 정리
    4. 공백 정리

    Returns:
        정제된 텍스트 또는 None (내용이 없는 경우)
    """
    if not raw_text:
        return None

    # 1. ANSI 코드 제거
    text = remove_ansi(raw_text)

    # 2. 노이즈 필터링
    text = filter_noise(text)

    # 3. 코드 블록 정리
    text = fix_code_blocks(text)

    # 4. 앞뒤 공백 정리
    text = text.strip()

    # 내용이 있으면 반환
    if text and len(text) > 0:
        return text

    return None


def clean_and_split(raw_text: str) -> list[str]:
    """
    터미널 출력을 정제하고 슬랙 메시지 크기로 분할

    Returns:
        분할된 메시지 리스트 (빈 경우 빈 리스트)
    """
    cleaned = clean_output(raw_text)
    if not cleaned:
        return []

    return split_message(cleaned)


# =============================================================================
# 특수 메시지 감지
# =============================================================================

def detect_tool_use(text: str) -> Optional[dict]:
    """
    Claude의 도구 사용 감지

    Returns:
        {"tool": "tool_name", "status": "running|completed|error"} 또는 None
    """
    # 도구 사용 패턴들
    tool_patterns = [
        (r'(?i)reading\s+file[:\s]+([^\n]+)', 'Read', 'running'),
        (r'(?i)writing\s+to\s+file[:\s]+([^\n]+)', 'Write', 'running'),
        (r'(?i)running\s+command[:\s]+([^\n]+)', 'Bash', 'running'),
        (r'(?i)searching[:\s]+([^\n]+)', 'Search', 'running'),
        (r'(?i)editing\s+file[:\s]+([^\n]+)', 'Edit', 'running'),
    ]

    for pattern, tool, status in tool_patterns:
        match = re.search(pattern, text)
        if match:
            return {
                "tool": tool,
                "target": match.group(1).strip(),
                "status": status
            }

    return None


def is_prompt_line(text: str) -> bool:
    """
    Claude가 입력을 기다리는 프롬프트인지 감지
    """
    prompt_patterns = [
        r'^\s*>\s*$',
        r'^\s*claude>\s*$',
        r'^\s*\$\s*$',
        r'human:',
        r'Human:',
    ]

    for pattern in prompt_patterns:
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            return True

    return False
