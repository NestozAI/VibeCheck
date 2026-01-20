#!/usr/bin/env python3
"""
VibeCheck Agent
- 중앙 서버에 WebSocket 연결
- 로컬에서 CLI 실행
- 결과를 서버로 전송
- 이미지 감지 및 업로드
- 경로 기반 보안 시스템
- PTY 모드: 터미널 UI를 그대로 웹에서 볼 수 있음
"""

import os
import sys
import asyncio
import argparse
import subprocess
import logging
import json
import re
import glob
import base64
# PTY 관련 import 제거됨 (Message 모드로 전환)
from typing import Optional, Set, List, Dict
from concurrent.futures import ThreadPoolExecutor

import websockets
from websockets.exceptions import ConnectionClosed

try:
    from html_screenshot import html_file_to_screenshot, screenshot_project, detect_project_type
    HAS_SCREENSHOT = True
except ImportError as e:
    HAS_SCREENSHOT = False
    print(f"⚠️ 스크린샷 기능 비활성화: {e}")
except Exception as e:
    HAS_SCREENSHOT = False
    print(f"⚠️ 스크린샷 기능 비활성화 (기타 오류): {e}")

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# 설정
# =============================================================================

# Railway 배포 URL
DEFAULT_SERVER = "wss://vibecheck.nestoz.co/ws/agent"

# 세션 파일 저장 디렉토리
SESSION_DIR = os.path.expanduser("~/.vibecheck")

# CLI 실행을 위한 스레드풀
executor = ThreadPoolExecutor(max_workers=1)

# 이미지 확장자
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}

# 안전한 시스템 명령어 (승인 없이 실행 가능)
SAFE_SYSTEM_COMMANDS = {
    'nvidia-smi', 'df', 'free', 'uptime', 'whoami', 'hostname',
    'cat /proc/cpuinfo', 'cat /proc/meminfo', 'ps', 'top -bn1',
    'ls', 'pwd', 'date', 'which', 'echo', 'git status', 'git log', 'git diff'
}


# =============================================================================
# 이미지 감지 유틸리티
# =============================================================================

def get_images_with_mtime(work_dir: str) -> Dict[str, float]:
    """작업 디렉토리의 이미지 파일과 수정 시간 반환"""
    images = {}
    for ext in IMAGE_EXTENSIONS:
        for path in glob.glob(os.path.join(work_dir, f'*{ext}')):
            images[path] = os.path.getmtime(path)
        for path in glob.glob(os.path.join(work_dir, f'**/*{ext}'), recursive=True):
            images[path] = os.path.getmtime(path)
    return images


def find_new_or_modified_images(work_dir: str, before_images: Dict[str, float]) -> List[str]:
    """새로 생성되거나 수정된 이미지 파일 찾기"""
    after_images = get_images_with_mtime(work_dir)
    result = []
    for path, mtime in after_images.items():
        if path not in before_images or mtime > before_images[path]:
            result.append(path)
    return result


def image_to_base64(image_path: str) -> Optional[str]:
    """이미지 파일을 base64로 인코딩"""
    try:
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except Exception as e:
        logger.error(f"이미지 인코딩 실패: {e}")
        return None


# =============================================================================
# 경로 보안 유틸리티
# =============================================================================

def normalize_path(path: str) -> str:
    """경로 정규화"""
    return os.path.normpath(os.path.abspath(os.path.expanduser(path)))


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

    # 중복 제거
    unique_paths = []
    seen = set()
    for p in paths:
        if p.startswith('.') and '/' not in p:
            continue
        normalized = normalize_path(p) if p.startswith('/') else p
        if normalized not in seen:
            seen.add(normalized)
            unique_paths.append(p)

    return unique_paths


def is_safe_system_command(message: str) -> bool:
    """안전한 시스템 명령어인지 확인"""
    msg_lower = message.lower().strip()
    for cmd in SAFE_SYSTEM_COMMANDS:
        if cmd in msg_lower:
            return True
    return False


# =============================================================================
# 세션 ID 관리
# =============================================================================

def get_session_file_path(work_dir: str) -> str:
    """작업 디렉토리에 대한 세션 파일 경로 반환"""
    # 디렉토리 경로를 해시하여 고유한 파일명 생성
    import hashlib
    dir_hash = hashlib.md5(work_dir.encode()).hexdigest()[:12]
    return os.path.join(SESSION_DIR, f"session_{dir_hash}.json")


def save_session_id(work_dir: str, session_id: str):
    """세션 ID 저장"""
    os.makedirs(SESSION_DIR, exist_ok=True)
    session_file = get_session_file_path(work_dir)
    data = {
        "work_dir": work_dir,
        "session_id": session_id,
        "updated_at": str(os.popen("date -Iseconds").read().strip())
    }
    try:
        with open(session_file, 'w') as f:
            json.dump(data, f)
        logger.info(f"세션 ID 저장: {session_id[:20]}...")
    except Exception as e:
        logger.warning(f"세션 ID 저장 실패: {e}")


def load_session_id(work_dir: str) -> Optional[str]:
    """저장된 세션 ID 로드"""
    session_file = get_session_file_path(work_dir)
    if os.path.exists(session_file):
        try:
            with open(session_file, 'r') as f:
                data = json.load(f)
                session_id = data.get("session_id")
                if session_id:
                    logger.info(f"이전 세션 ID 로드: {session_id[:20]}...")
                    return session_id
        except Exception as e:
            logger.warning(f"세션 ID 로드 실패: {e}")
    return None


def clear_session_id(work_dir: str):
    """세션 ID 삭제 (새 세션 시작 시)"""
    session_file = get_session_file_path(work_dir)
    if os.path.exists(session_file):
        try:
            os.remove(session_file)
            logger.info("이전 세션 ID 삭제됨")
        except Exception as e:
            logger.warning(f"세션 ID 삭제 실패: {e}")


class VibeAgent:
    """VibeCheck Agent"""

    def __init__(self, api_key: str, work_dir: str, server_url: str = DEFAULT_SERVER, new_session: bool = False):
        self.api_key = api_key
        self.work_dir = work_dir
        self.server_url = f"{server_url}?key={api_key}"
        self.session_started = False
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.processing = False  # CLI 실행 중 플래그

        # 신뢰 경로 (작업 디렉토리는 기본 신뢰)
        self.trusted_paths: Set[str] = {normalize_path(work_dir)}

        # 승인 대기 중인 요청
        self.pending_approval: Optional[dict] = None

        # 최근 작업한 프로젝트 경로 저장 (스크린샷 등에 사용)
        self.last_project_path: Optional[str] = None

        # 세션 ID 관리
        self.session_id: Optional[str] = None
        if new_session:
            clear_session_id(work_dir)
        else:
            self.session_id = load_session_id(work_dir)

    def is_path_trusted(self, path: str) -> bool:
        """경로가 신뢰할 수 있는지 확인"""
        normalized = normalize_path(path)
        for trusted in self.trusted_paths:
            if normalized == trusted or normalized.startswith(trusted + os.sep):
                return True
        return False

    def check_untrusted_paths(self, message: str) -> List[str]:
        """메시지에서 신뢰되지 않은 경로 찾기"""
        paths = extract_paths_from_message(message)
        untrusted = []
        for path in paths:
            if path.startswith('/'):
                if not self.is_path_trusted(path):
                    untrusted.append(path)
        return untrusted

    def add_trusted_path(self, path: str):
        """신뢰 경로 추가"""
        normalized = normalize_path(path)
        self.trusted_paths.add(normalized)
        logger.info(f"신뢰 경로 추가: {normalized}")

    def run_command_sync(self, message: str) -> str:
        """로컬에서 CLI 명령 실행 (동기, 스레드에서 실행됨)"""
        cmd = [
            "claude",
            "--print",
            "--dangerously-skip-permissions",
        ]

        # 세션 이어가기: 저장된 세션 ID가 있으면 --resume, 아니면 --continue
        if self.session_id:
            cmd.extend(["--resume", self.session_id])
        elif self.session_started:
            cmd.append("--continue")

        cmd.append(message)

        logger.info(f"명령 실행: {' '.join(cmd[:4])}...")

        try:
            result = subprocess.run(
                cmd,
                cwd=self.work_dir,
                capture_output=True,
                text=True,
                timeout=300,
                env={**os.environ, 'NO_COLOR': '1'}
            )

            if not self.session_started:
                self.session_started = True

            output = result.stdout
            if result.stderr:
                logger.warning(f"stderr: {result.stderr[:200]}")

            if result.returncode != 0:
                logger.error(f"CLI 실패: returncode={result.returncode}, stderr={result.stderr[:200] if result.stderr else 'None'}, stdout={result.stdout[:200] if result.stdout else 'None'}")
                # stderr가 없으면 stdout에 에러 메시지가 있을 수 있음
                error_msg = result.stderr or result.stdout or '알 수 없는 오류'

                # 세션 ID가 유효하지 않으면 새 세션 시작
                if self.session_id and ("session" in error_msg.lower() or "not found" in error_msg.lower()):
                    logger.warning("세션 ID가 유효하지 않음. 새 세션으로 재시도...")
                    self.session_id = None
                    clear_session_id(self.work_dir)
                    return self.run_command_sync(message)

                return f"오류: {error_msg}"

            # 첫 실행 후 세션 ID 추출 및 저장
            if not self.session_id:
                self._extract_and_save_session_id()

            logger.info(f"응답 ({len(output)}자): {output[:100]}...")
            return output

        except subprocess.TimeoutExpired:
            return "타임아웃 (5분 초과)"
        except Exception as e:
            logger.error(f"실행 오류: {e}")
            return f"실행 오류: {str(e)}"

    def _extract_and_save_session_id(self):
        """Claude Code의 최근 세션 ID 추출 및 저장 (프로젝트 디렉토리에서 직접)"""
        try:
            # Claude Code 프로젝트 디렉토리 경로 계산
            # ~/.claude/projects/-disk1-lecture-sotaaz-test-VibeCheck/
            work_dir_escaped = self.work_dir.replace('/', '-').lstrip('-')
            claude_project_dir = os.path.expanduser(f"~/.claude/projects/-{work_dir_escaped}")

            if not os.path.isdir(claude_project_dir):
                logger.debug(f"Claude 프로젝트 디렉토리 없음: {claude_project_dir}")
                return

            # 가장 최근 수정된 .jsonl 파일 찾기
            jsonl_files = glob.glob(os.path.join(claude_project_dir, "*.jsonl"))
            if not jsonl_files:
                logger.debug("세션 파일 없음")
                return

            # 수정 시간 기준 정렬
            latest_file = max(jsonl_files, key=os.path.getmtime)
            session_id = os.path.basename(latest_file).replace('.jsonl', '')

            # UUID 형식 검증 (간단히)
            if len(session_id) == 36 and session_id.count('-') == 4:
                self.session_id = session_id
                save_session_id(self.work_dir, session_id)
                logger.info(f"세션 ID 추출 성공: {session_id[:20]}...")
            else:
                logger.debug(f"유효하지 않은 세션 ID 형식: {session_id}")
        except Exception as e:
            logger.debug(f"세션 ID 추출 실패 (무시): {e}")

    async def run_command(self, message: str) -> str:
        """CLI 명령 실행 (비동기 래퍼)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, self.run_command_sync, message)

    def is_ws_open(self) -> bool:
        """WebSocket 연결 상태 확인 (websockets 12.0+ 호환)"""
        if not self.ws:
            return False
        try:
            # websockets 12.0+에서는 state 속성 사용
            from websockets.protocol import State
            return self.ws.state == State.OPEN
        except (AttributeError, ImportError):
            # 이전 버전 호환
            try:
                return not self.ws.closed
            except AttributeError:
                return True  # 확인 불가시 열려있다고 가정

    async def ping_loop(self):
        """주기적으로 ping 전송 (연결 유지)"""
        while True:
            try:
                await asyncio.sleep(15)  # 15초마다 ping
                if self.is_ws_open():
                    await self.ws.send(json.dumps({"type": "ping"}))
                    logger.debug("ping 전송")
            except ConnectionClosed:
                logger.debug("ping 중 연결 종료")
                break
            except Exception as e:
                logger.debug(f"ping 오류: {e}")
                break

    async def connect(self):
        """서버에 연결하고 메시지 처리"""
        logger.info(f"서버 연결 중: {self.server_url[:50]}...")

        try:
            async with websockets.connect(
                self.server_url,
                ping_interval=20,  # websockets 라이브러리 자체 ping
                ping_timeout=30
            ) as ws:
                self.ws = ws
                logger.info("서버 연결 성공!")

                # 연결 확인 메시지 대기
                response = await ws.recv()
                logger.info(f"서버 응답: {response}")

                print("\n" + "=" * 50)
                print("  VibeCheck Agent 실행 중")
                print(f"  작업 디렉토리: {self.work_dir}")
                print(f"  스크린샷 기능: {'✅ 활성화' if HAS_SCREENSHOT else '❌ 비활성화'}")
                print("  Slack에서 메시지를 보내세요!")
                print("  종료: Ctrl+C")
                print("=" * 50 + "\n")

                # ping 루프 시작
                ping_task = asyncio.create_task(self.ping_loop())

                try:
                    # 메시지 수신 대기
                    async for message in ws:
                        await self.handle_message(message)
                finally:
                    ping_task.cancel()

        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"서버 연결이 닫혔습니다: {e}")
        except Exception as e:
            logger.error(f"연결 오류: {e}")
            raise

    async def handle_message(self, raw_message: str):
        """서버에서 받은 메시지 처리"""
        data = json.loads(raw_message)
        msg_type = data.get("type")

        if msg_type == "query":
            # 사용자 쿼리 처리
            message = data.get("message", "")
            logger.info(f"쿼리 수신: {message[:50]}...")

            # 🛡️ 보안 검사: 신뢰되지 않은 경로 확인
            untrusted_paths = self.check_untrusted_paths(message)

            if untrusted_paths and not is_safe_system_command(message):
                # 승인 필요 - 서버에 승인 요청 전송
                logger.info(f"승인 필요: {untrusted_paths}")
                self.pending_approval = {"message": message, "paths": untrusted_paths}

                if self.is_ws_open():
                    await self.ws.send(json.dumps({
                        "type": "approval_required",
                        "paths": untrusted_paths,
                        "message": message[:200]  # 미리보기
                    }))
                return

            # CLI 실행
            await self.execute_and_respond(message)

        elif msg_type == "approval":
            # 서버에서 승인/거절 응답
            approved = data.get("approved", False)
            permanent = data.get("permanent", False)

            if self.pending_approval:
                if approved:
                    logger.info("승인됨! 명령 실행 중...")

                    # 영구 승인이면 경로 추가
                    if permanent:
                        for path in self.pending_approval.get("paths", []):
                            self.add_trusted_path(path)

                    # 실행
                    await self.execute_and_respond(self.pending_approval["message"])
                else:
                    logger.info("거절됨")
                    if self.is_ws_open():
                        await self.ws.send(json.dumps({
                            "type": "response",
                            "result": "❌ 요청이 거절되었습니다."
                        }))

                self.pending_approval = None

        elif msg_type == "add_trusted_path":
            # 서버에서 신뢰 경로 추가 요청
            path = data.get("path")
            if path:
                self.add_trusted_path(path)

        elif msg_type == "ping":
            await self.ws.send(json.dumps({"type": "pong"}))

        elif msg_type == "pong":
            pass  # 서버의 pong 응답

        elif msg_type == "error":
            logger.error(f"서버 오류: {data.get('message')}")

    async def execute_and_respond(self, message: str):
        """CLI 실행 및 응답 (이미지 감지 포함)"""
        self.processing = True

        # 실행 전 이미지 목록 저장
        before_images = get_images_with_mtime(self.work_dir)

        # CLI 실행 (비동기 - ping 루프가 계속 동작)
        result = await self.run_command(message)

        self.processing = False

        # 메시지에서 프로젝트 경로 추출 및 저장 (스크린샷용)
        path_pattern = r'(/[a-zA-Z0-9_\-./]+)'
        path_matches = re.findall(path_pattern, message)
        for path in path_matches:
            if os.path.isdir(path):
                # 디렉토리면 일단 저장 (프로젝트 타입 무관)
                self.last_project_path = path
                logger.info(f"프로젝트 경로 저장: {path}")
                break

        # 스크린샷 요청 감지 및 프로젝트 스크린샷 생성
        screenshot_keywords = ['스크린샷', 'screenshot', '캡처', 'capture', '보여줘', 'show me', 'preview', '미리보기', 'ui']
        wants_screenshot = any(kw in message.lower() for kw in screenshot_keywords)
        generated_screenshot = None  # 생성된 스크린샷 경로

        if wants_screenshot and HAS_SCREENSHOT:
            project_dir = None
            # 스크린샷은 /tmp에 저장 (권한 문제 방지)
            screenshot_path = '/tmp/vibecheck_screenshot.png'

            # 1. 메시지에서 프로젝트 경로 추출
            for path in path_matches:
                if os.path.isdir(path):
                    # 프로젝트 디렉토리인지 확인
                    project_info = detect_project_type(path)
                    if project_info["type"] != "unknown":
                        project_dir = path
                        logger.info(f"프로젝트 감지: {path} -> {project_info}")
                        break

            # 2. 저장된 프로젝트 경로 사용 (이전 대화 컨텍스트)
            if not project_dir and self.last_project_path and os.path.isdir(self.last_project_path):
                project_dir = self.last_project_path
                logger.info(f"저장된 프로젝트 경로 사용: {project_dir}")

            # 3. work_dir 확인
            if not project_dir:
                project_info = detect_project_type(self.work_dir)
                if project_info["type"] != "unknown":
                    project_dir = self.work_dir

            # 4. 응답에서 HTML 파일 경로 찾기 (폴백)
            if not project_dir:
                html_pattern = r'([a-zA-Z0-9_\-./]+\.html)'
                html_matches = re.findall(html_pattern, result)
                for html_file in html_matches:
                    if html_file.startswith('/'):
                        html_path = html_file
                    else:
                        html_path = os.path.join(self.work_dir, html_file)
                    if os.path.isfile(html_path):
                        try:
                            logger.info(f"HTML 파일 스크린샷 생성 중: {html_path}")
                            loop = asyncio.get_event_loop()
                            await loop.run_in_executor(
                                executor,
                                lambda hp=html_path: html_file_to_screenshot(hp, screenshot_path, width=1200, height=800, full_page=True)
                            )
                            logger.info(f"스크린샷 생성 완료: {screenshot_path}")
                            generated_screenshot = screenshot_path
                        except Exception as e:
                            logger.error(f"스크린샷 생성 실패: {e}")
                        break

            # 프로젝트 스크린샷 생성 (별도 스레드에서 실행 - Playwright Sync API는 asyncio와 호환 안됨)
            if project_dir:
                try:
                    logger.info(f"프로젝트 스크린샷 생성 중: {project_dir}")
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        executor,
                        lambda: screenshot_project(project_dir, screenshot_path, width=1200, height=800, full_page=True)
                    )
                    logger.info(f"스크린샷 생성 완료: {screenshot_path}")
                    generated_screenshot = screenshot_path
                except Exception as e:
                    logger.error(f"프로젝트 스크린샷 생성 실패: {e}")

        # 새로 생성된 이미지 감지
        new_images = find_new_or_modified_images(self.work_dir, before_images)
        images_data = []

        # 명시적으로 생성된 스크린샷 먼저 추가
        if generated_screenshot and os.path.isfile(generated_screenshot):
            b64 = image_to_base64(generated_screenshot)
            if b64:
                images_data.append({
                    "filename": "screenshot.png",
                    "data": b64
                })
                logger.info(f"스크린샷 이미지 추가: screenshot.png")
                # 스크린샷 파일 삭제 (임시 파일)
                try:
                    os.remove(generated_screenshot)
                    logger.info("스크린샷 파일 삭제됨")
                except:
                    pass

        for img_path in new_images[:5]:  # 최대 5개
            # 이미 추가된 스크린샷은 건너뛰기
            if generated_screenshot and img_path == generated_screenshot:
                continue
            b64 = image_to_base64(img_path)
            if b64:
                images_data.append({
                    "filename": os.path.basename(img_path),
                    "data": b64
                })
                logger.info(f"이미지 감지: {os.path.basename(img_path)}")

        # 이미지 전달 요청 키워드
        image_request_keywords = ['이미지', 'image', '전달', 'send', '보내', '첨부', 'attach']
        wants_image = any(kw in message.lower() for kw in image_request_keywords)

        # 응답에서 언급된 이미지 경로 추출 및 전송
        if not images_data or wants_image:  # 이미지가 없거나 명시적 요청 시
            # 1. 절대 경로 패턴
            img_path_pattern = r'(/[a-zA-Z0-9_\-./]+\.(?:png|jpg|jpeg|gif|webp|bmp))'
            mentioned_images = re.findall(img_path_pattern, result, re.IGNORECASE)

            # 메시지에서도 이미지 경로 추출
            msg_images = re.findall(img_path_pattern, message, re.IGNORECASE)
            mentioned_images = mentioned_images + msg_images

            # 2. 파일명만 있는 경우 (예: 01-hero.png)
            filename_pattern = r'[\s\-]([a-zA-Z0-9_\-]+\.(?:png|jpg|jpeg|gif|webp|bmp))'
            mentioned_filenames = re.findall(filename_pattern, result, re.IGNORECASE)

            added_paths = set()

            # 절대 경로 이미지 처리
            for img_path in mentioned_images[:10]:
                if img_path in added_paths:
                    continue
                if os.path.isfile(img_path):
                    b64 = image_to_base64(img_path)
                    if b64:
                        images_data.append({
                            "filename": os.path.basename(img_path),
                            "data": b64
                        })
                        added_paths.add(img_path)
                        logger.info(f"응답에서 이미지 추출: {os.path.basename(img_path)}")

            # 파일명만 있는 경우 - last_project_path에서 찾기
            if len(images_data) < 10 and self.last_project_path:
                search_dirs = [
                    self.last_project_path,
                    os.path.join(self.last_project_path, 'screenshots'),
                    os.path.join(self.last_project_path, 'images'),
                    os.path.join(self.last_project_path, 'assets'),
                ]
                for filename in mentioned_filenames[:10]:
                    if len(images_data) >= 10:
                        break
                    for search_dir in search_dirs:
                        if not os.path.isdir(search_dir):
                            continue
                        img_path = os.path.join(search_dir, filename)
                        if img_path in added_paths:
                            continue
                        if os.path.isfile(img_path):
                            b64 = image_to_base64(img_path)
                            if b64:
                                images_data.append({
                                    "filename": filename,
                                    "data": b64
                                })
                                added_paths.add(img_path)
                                logger.info(f"프로젝트 폴더에서 이미지 찾음: {filename}")
                            break

        # 결과 전송
        if self.is_ws_open():
            try:
                response_data = {
                    "type": "response",
                    "result": result
                }

                # 이미지가 있으면 함께 전송
                if images_data:
                    response_data["images"] = images_data
                    logger.info(f"{len(images_data)}개 이미지 전송")

                await self.ws.send(json.dumps(response_data))
                logger.info("응답 전송 완료")
            except ConnectionClosed:
                logger.error("응답 전송 중 연결 종료됨")
        else:
            logger.error("WebSocket이 닫혀서 응답 전송 실패")


async def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="VibeCheck Agent")
    parser.add_argument("--key", "-k", required=True, help="API Key")
    parser.add_argument("--dir", "-d", default=os.getcwd(), help="작업 디렉토리")
    parser.add_argument("--server", "-s", default=DEFAULT_SERVER, help="서버 URL")
    parser.add_argument("--new-session", "-n", action="store_true", help="새 세션 시작 (이전 세션 무시)")

    args = parser.parse_args()

    # 작업 디렉토리 확인
    if not os.path.isdir(args.dir):
        print(f"Error: 디렉토리가 존재하지 않습니다: {args.dir}")
        sys.exit(1)

    agent = VibeAgent(
        api_key=args.key,
        work_dir=args.dir,
        server_url=args.server,
        new_session=args.new_session
    )

    # 재연결 로직
    while True:
        try:
            await agent.connect()
        except KeyboardInterrupt:
            logger.info("종료합니다.")
            break
        except Exception as e:
            logger.error(f"연결 실패: {e}")
            logger.info("5초 후 재연결...")
            await asyncio.sleep(5)


def cli_main():
    """CLI entry point"""
    asyncio.run(main())


if __name__ == "__main__":
    cli_main()
