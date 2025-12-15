
import os
import subprocess
import threading
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# Claude 실행기
# =============================================================================

class ClaudeRunner:
    """
    Claude CLI를 subprocess로 실행

    --print 모드로 한 번에 실행하고 결과 반환
    --continue로 이전 대화 이어가기
    """

    def __init__(self, work_dir: str):
        self.work_dir = work_dir
        self.session_started = False  # 첫 메시지 이후 True
        self.lock = threading.Lock()

    def run(self, message: str, continue_session: bool = True) -> str:
        """
        Claude에 메시지 전송하고 응답 받기

        Args:
            message: 사용자 메시지
            continue_session: True면 --continue로 이전 대화 이어가기

        Returns:
            Claude의 응답 텍스트
        """
        with self.lock:
            # 기본 명령어
            cmd = [
                "claude",
                "--print",  # non-interactive 모드
                "--dangerously-skip-permissions",  # 권한 프롬프트 건너뛰기
            ]

            # 첫 메시지가 아니면 --continue 추가
            if continue_session and self.session_started:
                cmd.append("--continue")

            # 메시지 추가
            cmd.append(message)

            logger.info(f"Claude 실행: {' '.join(cmd[:4])}... '{message[:50]}...'")

            try:
                # subprocess 실행
                result = subprocess.run(
                    cmd,
                    cwd=self.work_dir,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5분 타임아웃
                    env={**os.environ, 'NO_COLOR': '1'}
                )

                # 첫 메시지 성공 후 세션 시작됨 표시
                if not self.session_started:
                    self.session_started = True

                # stdout과 stderr 합치기
                output = result.stdout
                if result.stderr:
                    logger.warning(f"Claude stderr: {result.stderr[:200]}")

                if result.returncode != 0:
                    logger.error(f"Claude 실행 실패 (code {result.returncode}): {result.stderr}")
                    return f"❌ Claude 오류: {result.stderr or '알 수 없는 오류'}"

                logger.info(f"Claude 응답 ({len(output)}자): {output[:100]}...")
                return output

            except subprocess.TimeoutExpired:
                logger.error("Claude 타임아웃 (5분)")
                return "❌ Claude 응답 타임아웃 (5분 초과)"
            except Exception as e:
                logger.error(f"Claude 실행 오류: {e}")
                return f"❌ Claude 실행 오류: {str(e)}"

    def reset_session(self):
        """세션 리셋 (새 대화 시작)"""
        with self.lock:
            self.session_started = False
            logger.info("Claude 세션 리셋됨")
