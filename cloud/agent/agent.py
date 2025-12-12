#!/usr/bin/env python3
"""
VibeCheck Agent
- 중앙 서버에 WebSocket 연결
- 로컬에서 CLI 실행
- 결과를 서버로 전송
"""

import os
import sys
import asyncio
import argparse
import subprocess
import logging
from typing import Optional

import websockets

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# 설정
# =============================================================================

# Render 배포 후 이 URL로 변경
DEFAULT_SERVER = "wss://vibecheck-cloud.onrender.com/ws/agent"


class VibeAgent:
    """VibeCheck Agent"""

    def __init__(self, api_key: str, work_dir: str, server_url: str = DEFAULT_SERVER):
        self.api_key = api_key
        self.work_dir = work_dir
        self.server_url = f"{server_url}?key={api_key}"
        self.session_started = False
        self.ws: Optional[websockets.WebSocketClientProtocol] = None

    def run_command(self, message: str) -> str:
        """로컬에서 CLI 명령 실행"""
        cmd = [
            "claude",
            "--print",
            "--dangerously-skip-permissions",
        ]

        if self.session_started:
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
                logger.warning(f"stderr: {result.stderr[:100]}")

            if result.returncode != 0:
                return f"오류: {result.stderr or '알 수 없는 오류'}"

            logger.info(f"응답 ({len(output)}자): {output[:100]}...")
            return output

        except subprocess.TimeoutExpired:
            return "타임아웃 (5분 초과)"
        except Exception as e:
            logger.error(f"실행 오류: {e}")
            return f"실행 오류: {str(e)}"

    async def connect(self):
        """서버에 연결하고 메시지 처리"""
        logger.info(f"서버 연결 중: {self.server_url[:50]}...")

        try:
            async with websockets.connect(self.server_url) as ws:
                self.ws = ws
                logger.info("서버 연결 성공!")

                # 연결 확인 메시지 대기
                response = await ws.recv()
                logger.info(f"서버 응답: {response}")

                print("\n" + "=" * 50)
                print("  VibeCheck Agent 실행 중")
                print(f"  작업 디렉토리: {self.work_dir}")
                print("  Slack에서 메시지를 보내세요!")
                print("  종료: Ctrl+C")
                print("=" * 50 + "\n")

                # 메시지 수신 대기
                async for message in ws:
                    await self.handle_message(message)

        except websockets.exceptions.ConnectionClosed:
            logger.warning("서버 연결이 닫혔습니다.")
        except Exception as e:
            logger.error(f"연결 오류: {e}")
            raise

    async def handle_message(self, raw_message: str):
        """서버에서 받은 메시지 처리"""
        import json
        data = json.loads(raw_message)

        msg_type = data.get("type")

        if msg_type == "query":
            # 사용자 쿼리 처리
            message = data.get("message", "")
            logger.info(f"쿼리 수신: {message[:50]}...")

            # CLI 실행
            result = self.run_command(message)

            # 결과 전송
            await self.ws.send(json.dumps({
                "type": "response",
                "result": result
            }))
            logger.info("응답 전송 완료")

        elif msg_type == "ping":
            await self.ws.send(json.dumps({"type": "pong"}))

        elif msg_type == "error":
            logger.error(f"서버 오류: {data.get('message')}")


async def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="VibeCheck Agent")
    parser.add_argument("--key", "-k", required=True, help="API Key")
    parser.add_argument("--dir", "-d", default=os.getcwd(), help="작업 디렉토리")
    parser.add_argument("--server", "-s", default=DEFAULT_SERVER, help="서버 URL")

    args = parser.parse_args()

    # 작업 디렉토리 확인
    if not os.path.isdir(args.dir):
        print(f"Error: 디렉토리가 존재하지 않습니다: {args.dir}")
        sys.exit(1)

    agent = VibeAgent(
        api_key=args.key,
        work_dir=args.dir,
        server_url=args.server
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


if __name__ == "__main__":
    asyncio.run(main())
