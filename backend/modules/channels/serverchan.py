"""Server酱推送渠道：只出不进的消息推送，按 SendKey 前缀（SCT/SC3）自动识别端点；文档 https://sct.ftqq.com/docs/。"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, Optional

import httpx
from loguru import logger

from backend.modules.channels.base import BaseChannel, OutboundMessage

SCT_ENDPOINT_TEMPLATE = "https://sctapi.ftqq.com/{sendkey}.send"
SC3_ENDPOINT_TEMPLATE = "https://{uid}.push.ft07.com/send/{sendkey}.send"
SC3_SENDKEY_PATTERN = re.compile(r"sctp(\d+)t", re.IGNORECASE)

# Server酱标题不能含换行且有长度限制，正文有体积上限，超出会被上游拒绝，这里先行收敛。
TITLE_MAX_CHARS = 64
DESP_MAX_CHARS = 20000
REQUEST_TIMEOUT_SECONDS = 15.0


def resolve_serverchan_endpoint(sendkey: str) -> str:
    """按 SendKey 前缀解析推送端点，无法识别时抛 ``ValueError``。"""
    key = str(sendkey or "").strip()
    if not key:
        raise ValueError("SendKey 未配置")
    if key.lower().startswith("sctp"):
        match = SC3_SENDKEY_PATTERN.match(key)
        if not match:
            raise ValueError("SendKey 格式无效：SC3 密钥应为 sctp<uid>t... 形式")
        return SC3_ENDPOINT_TEMPLATE.format(uid=match.group(1), sendkey=key)
    return SCT_ENDPOINT_TEMPLATE.format(sendkey=key)


def build_serverchan_payload(content: str, *, title: Optional[str] = None) -> Dict[str, str]:
    """把一段消息正文拆成 Server酱要求的 ``title`` + ``desp``。"""
    text = str(content or "").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    final_title = str(title or (lines[0] if lines else "")).replace("\n", " ").strip()
    if not final_title:
        final_title = "CountBot 通知"
    if len(final_title) > TITLE_MAX_CHARS:
        final_title = final_title[: TITLE_MAX_CHARS - 1] + "…"

    desp = text
    if len(desp) > DESP_MAX_CHARS:
        desp = desp[:DESP_MAX_CHARS] + "\n\n…（内容过长已截断）"
    return {"title": final_title, "desp": desp}


class ServerChanChannel(BaseChannel):
    """Server酱推送渠道：只负责出站推送，``start`` 仅校验凭据、不建立长连接。"""

    name = "serverchan"

    def __init__(self, config: Any):
        super().__init__(config)
        self._delivery_error: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """推送渠道无需长连接，凭据合法即视为可投递。"""
        try:
            resolve_serverchan_endpoint(getattr(self.config, "sendkey", ""))
        except ValueError as e:
            self._running = False
            self.set_runtime_state(self.RUNTIME_FAILED, error=str(e))
            logger.warning(f"[{self._instance_key}] Server酱不可用：{e}")
            return

        self._running = True
        self.set_runtime_state(self.RUNTIME_RUNNING)

    async def stop(self) -> None:
        self._running = False
        self.set_runtime_state(self.RUNTIME_STOPPED)

    async def test_connection(self) -> Dict[str, Any]:
        """实际推送一条测试消息，验证 SendKey 与端点是否可用。"""
        try:
            endpoint = resolve_serverchan_endpoint(getattr(self.config, "sendkey", ""))
        except ValueError as e:
            return {"success": False, "message": str(e)}

        try:
            await self._push(
                endpoint,
                build_serverchan_payload(
                    "Server酱配置测试，收到本条消息即表示推送可用。",
                    title="CountBot 渠道测试",
                ),
            )
        except Exception as e:
            return {"success": False, "message": f"推送失败：{e}"}

        return {
            "success": True,
            "message": "测试消息已推送，请在微信或 Server酱³ App 中查看",
            "bot_info": {"status": "connected", "note": "已发送一条测试消息"},
        }

    # ------------------------------------------------------------------
    # 出站消息发送
    # ------------------------------------------------------------------

    async def send(self, msg: OutboundMessage) -> None:
        """通过 Server酱推送一条消息。"""
        try:
            endpoint = resolve_serverchan_endpoint(getattr(self.config, "sendkey", ""))
        except ValueError as e:
            self._record_delivery_error("send", error=e)
            return

        title = (msg.metadata or {}).get("title")
        payload = build_serverchan_payload(msg.content, title=title)
        try:
            await self._push(endpoint, payload)
        except Exception as e:
            self._record_delivery_error("send", error=e)
            return
        self._clear_delivery_error()
        logger.debug(f"[{self._instance_key}] Server酱推送成功：{payload['title']}")

    async def _push(self, endpoint: str, payload: Dict[str, str]) -> None:
        """执行一次推送；``code`` 非 0 时按失败处理。"""
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, trust_env=False) as client:
            response = await client.post(
                endpoint,
                json=payload,
                headers={"Content-Type": "application/json;charset=utf-8"},
            )
            response.raise_for_status()

        try:
            data = response.json()
        except ValueError:
            data = {}

        if data and data.get("code") not in (0, None):
            raise RuntimeError(str(data.get("message") or data.get("info") or f"code={data.get('code')}"))

    # ------------------------------------------------------------------
    # 消息投递诊断
    # ------------------------------------------------------------------

    def get_runtime_status(self) -> Dict[str, Any]:
        """在统一运行时状态上追加最近一次投递失败诊断。"""
        status = super().get_runtime_status()
        status["delivery_error"] = dict(self._delivery_error) if self._delivery_error else None
        return status

    def _record_delivery_error(self, operation: str, *, error: Exception) -> None:
        """记录最近一次投递失败，供设置页和运行状态展示。"""
        self._delivery_error = {
            "operation": operation,
            "at": time.time(),
            "error": str(error),
        }
        logger.error(f"[{self._instance_key}] Server酱投递失败 operation={operation}: {error}")

    def _clear_delivery_error(self) -> None:
        if self._delivery_error:
            self._delivery_error = {}
