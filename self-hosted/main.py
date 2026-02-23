"""
VibeCheck Self-Hosted
Web UI (default) + Slack integration (optional)
"""

import logging
import threading

import uvicorn

from config import SLACK_ENABLED, WEB_PORT, WEB_HOST, WORK_DIR
from security import get_trusted_paths

logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 50)
    logger.info("VibeCheck Self-Hosted starting!")
    logger.info(f"Working directory: {WORK_DIR}")
    logger.info(f"Trusted paths: {get_trusted_paths()}")
    logger.info(f"Web UI: http://{WEB_HOST}:{WEB_PORT}")
    logger.info(f"Slack: {'enabled' if SLACK_ENABLED else 'disabled'}")
    logger.info("=" * 50)

    from web_server import app as web_app, core

    # Start Slack handler in background thread (if tokens configured)
    if SLACK_ENABLED:
        try:
            from slack_handler import create_slack_app
            slack_handler = create_slack_app(core)
            slack_thread = threading.Thread(target=slack_handler.start, daemon=True)
            slack_thread.start()
            logger.info("Slack handler started in background")
        except ImportError:
            logger.warning(
                "Slack tokens configured but slack-bolt not installed. "
                "Run: pip install slack-bolt slack-sdk"
            )
        except Exception as e:
            logger.error(f"Failed to start Slack handler: {e}")

    # Start web server (main thread)
    uvicorn.run(web_app, host=WEB_HOST, port=WEB_PORT, log_level="info")


if __name__ == "__main__":
    main()
