"""
Terminal Output Cleaner
- ANSI escape code removal
- Noise filtering (spinners, progress indicators, etc.)
- Slack-compatible formatting
"""

import re
from typing import Optional

# =============================================================================
# ANSI escape code removal
# =============================================================================

# ANSI escape sequence patterns
ANSI_PATTERNS = [
    r'\x1b\[[0-9;]*[a-zA-Z]',      # CSI sequences: \x1b[0m, \x1b[1;32m etc.
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

# Combined pattern (performance optimization)
ANSI_REGEX = re.compile('|'.join(ANSI_PATTERNS))


def remove_ansi(text: str) -> str:
    """
    Completely remove ANSI escape codes.

    Removes all control characters including terminal colors, cursor movement, scrolling, etc.
    """
    return ANSI_REGEX.sub('', text)


# =============================================================================
# Noise filtering
# =============================================================================

# Patterns to ignore (progress indicators, spinners, loading messages, etc.)
NOISE_PATTERNS = [
    # Spinner characters
    r'^[\s]*[/\\|─━\-⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏●○◐◑◒◓][\s]*$',
    # Progress indicator messages (case insensitive handled in function)
    r'^[\s]*(loading|processing|thinking|waiting|connecting|initializing|Loading|Processing|Thinking|Waiting|Connecting|Initializing)\.{0,3}[\s]*$',
    # Empty lines or whitespace-only lines
    r'^[\s]*$',
    # Cursor-related output
    r'^\s*\d+;\d+[HR]',
    # Progress bar
    r'[\[█▓▒░\]]{3,}',
    r'\d+%\s*[\[█▓▒░\]]*',
    # Claude Code specific noise
    r'^[\s]*›[\s]*$',
    r'^[\s]*\.\.\.$',
    r'^\s*⠋\s*',
    r'^\s*⠙\s*',
    r'^\s*⠹\s*',
    # Repeated dots
    r'^\.+$',
]


def is_noise_line(line: str) -> bool:
    """Determine if a line is noise"""
    cleaned = line.strip()

    # Empty line
    if not cleaned:
        return True

    # Only spinner characters
    spinner_chars = set('/\\|─━-⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏●○◐◑◒◓')
    if all(c in spinner_chars or c.isspace() for c in cleaned):
        return True

    # Noise pattern matching
    for pattern in NOISE_PATTERNS:
        if re.match(pattern, cleaned, re.IGNORECASE):
            return True

    return False


def filter_noise(text: str) -> str:
    """
    Remove noise lines.

    Removes unnecessary output such as spinners, loading messages, progress indicators, etc.
    """
    lines = text.split('\n')
    filtered_lines = [line for line in lines if not is_noise_line(line)]

    # Clean up consecutive empty lines (max 1)
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
# Code block processing
# =============================================================================

def fix_code_blocks(text: str) -> str:
    """
    Clean up code block formatting.

    - Normalize language tags
    - Handle nested backticks
    - Convert to Slack-compatible format
    """
    # Keep existing code blocks
    # Check ```language ... ``` format

    # Find code blocks starting with triple backticks
    code_block_pattern = r'```(\w*)\n?(.*?)```'

    def format_code_block(match):
        lang = match.group(1) or ''
        code = match.group(2)
        # Slack doesn't support language highlighting, but keep the format
        return f'```{lang}\n{code.strip()}\n```'

    text = re.sub(code_block_pattern, format_code_block, text, flags=re.DOTALL)

    return text


# =============================================================================
# Slack message splitting
# =============================================================================

SLACK_MAX_LENGTH = 3900  # Slack message max length (under 4000 with buffer)


def split_message(text: str, max_length: int = SLACK_MAX_LENGTH) -> list[str]:
    """
    Split long messages to fit Slack limits.

    Ensures code blocks are not split in the middle.
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    current_chunk = ""
    in_code_block = False
    code_block_lang = ""

    lines = text.split('\n')

    for line in lines:
        # Detect code block start/end
        if line.strip().startswith('```'):
            if not in_code_block:
                # Code block start
                in_code_block = True
                code_block_lang = line.strip()[3:]
            else:
                # Code block end
                in_code_block = False
                code_block_lang = ""

        # Check length when adding line to current chunk
        test_chunk = current_chunk + line + '\n'

        if len(test_chunk) > max_length:
            # Chunk split needed
            if in_code_block and current_chunk:
                # If inside a code block, close it first
                current_chunk += '```\n'
                chunks.append(current_chunk.strip())
                # Reopen in new chunk
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
# Main cleaning function
# =============================================================================

def clean_output(raw_text: str) -> Optional[str]:
    """
    Clean terminal output for sending to Slack.

    1. Remove ANSI codes
    2. Filter noise
    3. Clean up code blocks
    4. Trim whitespace

    Returns:
        Cleaned text or None (if no content)
    """
    if not raw_text:
        return None

    # 1. Remove ANSI codes
    text = remove_ansi(raw_text)

    # 2. Filter noise
    text = filter_noise(text)

    # 3. Clean up code blocks
    text = fix_code_blocks(text)

    # 4. Trim leading/trailing whitespace
    text = text.strip()

    # Return if there is content
    if text and len(text) > 0:
        return text

    return None


def clean_and_split(raw_text: str) -> list[str]:
    """
    Clean terminal output and split into Slack message-sized chunks.

    Returns:
        List of split messages (empty list if no content)
    """
    cleaned = clean_output(raw_text)
    if not cleaned:
        return []

    return split_message(cleaned)


# =============================================================================
# Special message detection
# =============================================================================

def detect_tool_use(text: str) -> Optional[dict]:
    """
    Detect Claude's tool usage.

    Returns:
        {"tool": "tool_name", "status": "running|completed|error"} or None
    """
    # Tool usage patterns
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
    Detect if Claude is waiting for input at a prompt.
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
