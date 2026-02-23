"""
VibeCheck Web Server - FastAPI + WebSocket.
Serves the chat UI and handles real-time communication.
"""

import asyncio
import base64
import json
import logging
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from core import VibeCheckCore

logger = logging.getLogger(__name__)

app = FastAPI(title="VibeCheck")
core = VibeCheckCore()

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    logger.info("WebSocket client connected")

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            await _handle_message(ws, msg)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


async def _handle_message(ws: WebSocket, msg: dict):
    msg_type = msg.get("type")

    if msg_type == "query":
        await _handle_query(ws, msg.get("message", ""))
    elif msg_type == "approval":
        await _handle_approval(
            ws,
            msg.get("task_id", ""),
            msg.get("approved", False),
            msg.get("permanent", False),
        )
    elif msg_type == "ping":
        await ws.send_json({"type": "pong"})
    else:
        await ws.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})


async def _handle_query(ws: WebSocket, message: str):
    if not message.strip():
        await ws.send_json({"type": "error", "message": "Empty message"})
        return

    await ws.send_json({
        "type": "tool_status",
        "tool": "Claude",
        "status": "start",
        "label": "Claude is thinking...",
    })

    result_text = ""
    image_paths: list = []
    approval_data: dict | None = None

    def on_thinking():
        pass  # already sent tool_status above

    def on_response(text: str):
        nonlocal result_text
        result_text = text

    def on_images(paths: list):
        image_paths.extend(paths)

    def on_approval_required(task_id: str, paths: list, user_msg: str):
        nonlocal approval_data
        approval_data = {
            "type": "approval_required",
            "task_id": task_id,
            "paths": paths,
            "message": user_msg[:200],
        }

    await asyncio.to_thread(
        core.handle_message,
        message,
        "en",
        on_thinking=on_thinking,
        on_response=on_response,
        on_images=on_images,
        on_approval_required=on_approval_required,
    )

    await ws.send_json({
        "type": "tool_status",
        "tool": "Claude",
        "status": "end",
        "label": "Done",
    })

    if approval_data:
        await ws.send_json(approval_data)
        return

    response_msg: dict = {
        "type": "response",
        "result": result_text or "No response.",
    }

    if image_paths:
        response_msg["images"] = _encode_images(image_paths)

    await ws.send_json(response_msg)


async def _handle_approval(ws: WebSocket, task_id: str, approved: bool, permanent: bool):
    if not approved:
        from security import pending_tasks, pending_tasks_lock
        with pending_tasks_lock:
            pending_tasks.pop(task_id, None)
        await ws.send_json({"type": "response", "result": "Request denied."})
        return

    await ws.send_json({
        "type": "tool_status",
        "tool": "Claude",
        "status": "start",
        "label": "Approved! Claude is running...",
    })

    result_text = ""
    image_paths: list = []

    def on_response(text: str):
        nonlocal result_text
        result_text = text

    def on_images(paths: list):
        image_paths.extend(paths)

    await asyncio.to_thread(
        core.execute_pending_task,
        task_id,
        permanent,
        "en",
        on_response=on_response,
        on_images=on_images,
    )

    await ws.send_json({
        "type": "tool_status",
        "tool": "Claude",
        "status": "end",
        "label": "Done",
    })

    response_msg: dict = {
        "type": "response",
        "result": result_text or "No response.",
    }
    if image_paths:
        response_msg["images"] = _encode_images(image_paths)

    await ws.send_json(response_msg)


def _encode_images(paths: list) -> list:
    """Convert image file paths to base64 data for WebSocket transport."""
    images = []
    for img_path in paths:
        try:
            with open(img_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            ext = os.path.splitext(img_path)[1].lower().lstrip(".")
            mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "gif": "image/gif", "webp": "image/webp", "svg": "image/svg+xml",
                    "bmp": "image/bmp"}.get(ext, "image/png")
            images.append({
                "filename": os.path.basename(img_path),
                "data": b64,
                "mime": mime,
            })
        except Exception as e:
            logger.warning(f"Failed to read image {img_path}: {e}")
    return images
