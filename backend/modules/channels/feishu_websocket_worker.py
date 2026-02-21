"""飞书 WebSocket 独立进程

在完全独立的进程中运行飞书 WebSocket 连接，避免事件循环冲突。
使用 multiprocessing.Queue 进行进程间通信。
"""

import json
import os
import signal
import sys

from loguru import logger

# Worker 进程独立的日志配置
logger.remove()
logger.add(
    "data/logs/feishu_worker_{time}.log",
    rotation="1 day",
    retention="7 days",
    level="INFO",
)
logger.add(sys.stderr, level="INFO")

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
except ImportError:
    logger.error("lark-oapi not installed")
    sys.exit(1)


class FeishuWebSocketWorker:
    """飞书 WebSocket Worker

    在独立进程中运行 WebSocket 连接，接收消息后通过 Queue 传递给主进程。
    """

    def __init__(self, app_id: str, app_secret: str, message_queue):
        self.app_id = app_id
        self.app_secret = app_secret
        self.message_queue = message_queue
        self.ws_client = None
        self._running = False
        logger.info(f"Worker initialized (PID: {os.getpid()})")

    # ------------------------------------------------------------------
    # 消息处理
    # ------------------------------------------------------------------

    def on_message(self, data: P2ImMessageReceiveV1) -> None:
        """消息处理器 - 将消息放入队列供主进程读取。"""
        try:
            event = data.event
            message = event.message
            sender = event.sender

            msg_data = {
                "type": "message",
                "message_id": message.message_id,
                "sender_id": sender.sender_id.open_id if sender.sender_id else "unknown",
                "chat_id": message.chat_id,
                "chat_type": message.chat_type,
                "msg_type": message.message_type,
                "content": message.content,
            }

            try:
                self.message_queue.put_nowait(msg_data)
                logger.info(f"Message queued: {msg_data['message_id']}")
            except Exception as e:
                logger.warning(f"Queue full, message dropped: {e}")

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            try:
                self.message_queue.put_nowait({"type": "error", "error": str(e)})
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self) -> None:
        """启动 WebSocket 连接。"""
        logger.info(f"Starting Feishu WebSocket worker (app: {self.app_id[:12]}...)")

        try:
            self.message_queue.put_nowait({"type": "status", "message": "Worker started"})
        except Exception:
            pass

        event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self.on_message)
            .build()
        )

        self.ws_client = lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )

        self._running = True
        logger.info("WebSocket connecting...")

        try:
            self.message_queue.put_nowait({"type": "status", "message": "WebSocket connecting..."})
        except Exception:
            pass

        try:
            self.ws_client.start()
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
            self.stop()
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            try:
                self.message_queue.put_nowait({"type": "error", "error": f"WebSocket error: {e}"})
            except Exception:
                pass
            self.stop()
            raise

    def stop(self) -> None:
        """停止 WebSocket 连接。"""
        if self._running:
            logger.info("Stopping WebSocket worker...")
            self._running = False
            if self.ws_client:
                try:
                    self.ws_client.stop()
                except Exception as e:
                    logger.error(f"Error stopping WebSocket: {e}")
            logger.info("WebSocket worker stopped")


# ------------------------------------------------------------------
# 进程入口
# ------------------------------------------------------------------


def run_worker(app_id: str, app_secret: str, message_queue) -> None:
    """Worker 进程入口函数。"""
    logger.info(f"Worker process starting (PID: {os.getpid()}, app: {app_id[:12]}...)")

    worker = FeishuWebSocketWorker(app_id, app_secret, message_queue)

    def _signal_handler(signum, frame):
        logger.info(f"Received signal {signum}")
        worker.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    try:
        worker.start()
    except Exception as e:
        logger.error(f"Worker error: {e}")
        import traceback

        logger.error(traceback.format_exc())
        sys.exit(1)


# 兼容命令行调用（用于测试）
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python feishu_websocket_worker.py <app_id> <app_secret>")
        sys.exit(1)

    from multiprocessing import get_context

    ctx = get_context("spawn")
    test_queue = ctx.Queue(maxsize=1000)
    logger.info("Running in standalone test mode")
    run_worker(sys.argv[1], sys.argv[2], test_queue)
