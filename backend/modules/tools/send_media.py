"""发送媒体文件工具"""

import contextvars
import json
from pathlib import Path
from typing import Any, List, Optional, Tuple
from loguru import logger

from backend.modules.tools.base import Tool


IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}

FILE_EXTENSIONS = {
    '.txt', '.pdf', '.doc', '.docx', '.xls', '.xlsx', 
    '.ppt', '.pptx', '.zip', '.rar', '.7z',
    '.mp3', '.mp4', '.avi', '.mov',
    '.json', '.xml', '.csv', '.md'
}

_message_context_var: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "send_media_message_context",
    default=None,
)

WECOM_REPLY_IMAGE_MAX_BYTES = 10 * 1024 * 1024
WECOM_REPLY_IMAGE_MAX_COUNT = 10


class SendMediaTool(Tool):
    """发送媒体文件到频道工具"""
    
    name = "send_media"
    description = """发送文件或图片到当前聊天频道。

重要：当用户要求发送、分享、传送文件或图片时，必须使用此工具！

用法:
- send_media(file_paths=["report.pdf"], message="报告文档")
- send_media(file_paths=["chart.png"], message="数据图表")
- send_media(file_paths=["file1.pdf", "file2.png"])

支持格式:
- 图片: PNG, JPG, JPEG, GIF, BMP, WEBP
- 文档: PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT
- 压缩: ZIP, RAR, 7Z
- 媒体: MP3, MP4, AVI, MOV
- 数据: JSON, XML, CSV, MD

限制:
- 仅支持频道会话
- 企业微信长连接仅支持在当前回复中发送图片，不支持回传文件
- 单个文件最大 20MB

注意：不要只是说"文件已发送"，必须实际调用此工具！
"""
    
    parameters = {
        "type": "object",
        "properties": {
            "file_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "文件路径列表"
            },
            "message": {
                "type": "string",
                "description": "可选的文本说明",
                "default": ""
            }
        },
        "required": ["file_paths"]
    }
    
    def __init__(self, channel_manager=None, session_manager=None):
        super().__init__()
        self.channel_manager = channel_manager
        self.session_manager = session_manager
        self._current_session_id = None
    
    def set_session_id(self, session_id: str):
        """设置当前会话 ID"""
        self._current_session_id = session_id

    def set_message_context(self, message_context: Optional[dict]) -> None:
        """设置当前入站消息上下文。"""
        _message_context_var.set(message_context)

    def _is_image_file(self, file_path: Path) -> bool:
        """判断是否为图片文件"""
        return file_path.suffix.lower() in IMAGE_EXTENSIONS
    
    def _is_supported_file(self, file_path: Path) -> bool:
        """判断是否为支持的文件格式"""
        ext = file_path.suffix.lower()
        return ext in IMAGE_EXTENSIONS or ext in FILE_EXTENSIONS

    async def _prepare_media_path(self, file_path: Path, channel: str) -> Optional[str]:
        """为各渠道准备发送路径。

        当前已实现渠道统一支持直接传递本地文件路径，由具体 channel 自行上传。
        """
        _ = channel
        return str(file_path)

    
    async def _parse_session_info(self) -> Optional[Tuple[str, str, dict]]:
        """从会话名称解析频道和聊天 ID
        
        会话名称格式:
        - 频道会话: {channel}:{chat_id}:{timestamp}
        - 多机器人会话: {channel}:{account_id}:{chat_id}:{timestamp}
        - 网页会话: New Chat 2026/2/12 19:02:11 (不支持)
        """
        if not self._current_session_id:
            logger.warning("No session ID set")
            return None
        
        try:
            from backend.database import AsyncSessionLocal
            from backend.models.session import Session
            from sqlalchemy import select
            
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Session).where(Session.id == self._current_session_id)
                )
                session = result.scalar_one_or_none()
                
                if not session or not session.name:
                    logger.warning(f"Session not found: {self._current_session_id}")
                    return None
                
                if ':' not in session.name:
                    logger.info(f"Non-channel session: {session.name}")
                    return None
                
                parts = session.name.split(':')
                raw_context = getattr(session, "channel_context", None)
                channel_context = None
                if raw_context:
                    try:
                        channel_context = json.loads(raw_context)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid channel_context for session {session.id}")

                if len(parts) >= 3:
                    channel = parts[0]
                    if channel_context and channel_context.get("chat_id"):
                        chat_id = str(channel_context["chat_id"])
                    elif len(parts) >= 4:
                        chat_id = parts[2]
                    else:
                        chat_id = parts[1]

                    valid_channels = {'feishu', 'qq', 'wechat', 'dingtalk', 'telegram', 'discord', 'wecom'}
                    if channel not in valid_channels:
                        logger.warning(f"Invalid channel: {channel}")
                        return None

                    metadata = {}
                    account_id = None
                    if channel_context:
                        account_id = str(channel_context.get("account_id") or "").strip() or None
                    elif len(parts) >= 4:
                        account_id = parts[1]

                    if account_id:
                        metadata["account_id"] = account_id

                    if channel == "wecom":
                        if channel_context:
                            metadata["wecom_session_context"] = channel_context
                        else:
                            metadata["wecom_session_context"] = {
                                "channel": "wecom",
                                "account_id": account_id or "default",
                                "sender_id": chat_id,
                                "chat_id": chat_id,
                                "is_group": False,
                                "delivery_mode": "user",
                                "to_user": chat_id,
                                "group_chat_id": None,
                            }

                    logger.info(
                        f"Parsed session '{session.name}' -> "
                        f"channel='{channel}', account_id='{account_id}', chat_id='{chat_id}'"
                    )
                    return (channel, chat_id, metadata)
                
                logger.warning(f"Invalid session name format: {session.name}")
                return None
                
        except Exception as e:
            logger.error(f"Error parsing session info: {e}")
            return None
    
    async def execute(self, file_paths: List[str], message: str = "") -> str:
        """执行发送媒体文件"""
        try:
            if not self.channel_manager:
                return "错误：频道管理器未初始化"
            
            session_info = await self._parse_session_info()
            if not session_info:
                return (
                    "错误：此工具仅支持频道会话使用\n\n"
                    "当前环境不支持发送文件，可能原因：\n"
                    "- 在网页版或终端界面对话\n"
                    "- 未连接到支持的频道（飞书/QQ/钉钉/企业微信）\n\n"
                    "请在频道会话中使用此功能"
                )
            
            channel, chat_id, metadata = session_info
            logger.info(f"Sending media to {channel}:{chat_id}")
            
            valid_paths = []
            invalid_files = []
            image_count = 0
            file_count = 0
            
            for path in file_paths:
                file_path = Path(path)
                if not file_path.exists():
                    invalid_files.append(f"{path} (不存在)")
                    continue
                
                if not self._is_supported_file(file_path):
                    invalid_files.append(f"{path} (格式不支持)")
                    continue
                
                file_size = file_path.stat().st_size
                if file_size > 20 * 1024 * 1024:
                    invalid_files.append(f"{path} (超过 20MB)")
                    continue
                
                processed_path = await self._prepare_media_path(file_path, channel)
                if not processed_path:
                    invalid_files.append(f"{path} (预处理失败)")
                    continue
                
                valid_paths.append(processed_path)
                if self._is_image_file(file_path):
                    image_count += 1
                else:
                    file_count += 1
            
            if not valid_paths:
                error_msg = "没有有效的文件"
                if invalid_files:
                    error_msg += f"。无效文件: {', '.join(invalid_files)}"
                return error_msg

            if channel == "wecom":
                return self._queue_wecom_longconn_media(valid_paths, invalid_files, message)

            from backend.modules.channels.base import OutboundMessage
            
            if not message:
                if image_count > 0 and file_count == 0:
                    message = f"发送 {image_count} 个文件"
                elif file_count > 0 and image_count == 0:
                    message = f"发送 {file_count} 个文件"
                else:
                    message = f"发送 {len(valid_paths)} 个文件"
            
            outbound_msg = OutboundMessage(
                channel=channel,
                chat_id=chat_id,
                content=message,
                media=valid_paths,
                metadata=metadata
            )
            
            direct_channel = self.channel_manager.get_channel(
                channel,
                account_id=str(metadata.get("account_id") or "") or None,
            )
            if direct_channel:
                await direct_channel.send(outbound_msg)
            else:
                await self.channel_manager.send_message(outbound_msg)
            
            logger.info(f"Successfully sent {len(valid_paths)} files to {channel}:{chat_id}")
            
            if len(valid_paths) == 1:
                file_name = Path(valid_paths[0]).name
                result_msg = f"成功发送文件: {file_name}"
            else:
                result_msg = f"成功发送 {len(valid_paths)} 个文件到 {channel}"
            
            if invalid_files:
                result_msg += f"\n跳过 {len(invalid_files)} 个无效文件: {', '.join(invalid_files)}"
            
            return result_msg
            
        except Exception as e:
            logger.error(f"发送文件失败: {e}")
            return f"发送文件失败: {str(e)}"

    def _queue_wecom_longconn_media(
        self,
        valid_paths: List[str],
        invalid_files: List[str],
        message: str = "",
    ) -> str:
        """企业微信长连接模式下，将图片挂到当前被动回复上下文。"""
        message_context = _message_context_var.get() or {}
        metadata = message_context.get("metadata")
        if metadata is None:
            metadata = {}
        stream_handler = metadata.get("_stream_handler")

        if not stream_handler:
            return (
                "企业微信长连接模式当前没有可用的回复上下文，"
                "暂时只能在收到用户消息后的本轮回复中发送图片。"
            )

        image_paths = [path for path in valid_paths if self._is_image_file(Path(path))]
        file_paths = [path for path in valid_paths if not self._is_image_file(Path(path))]
        accepted_image_paths: List[str] = []
        oversized_images: List[str] = []

        for path in image_paths:
            try:
                if Path(path).stat().st_size > WECOM_REPLY_IMAGE_MAX_BYTES:
                    oversized_images.append(Path(path).name)
                else:
                    accepted_image_paths.append(path)
            except OSError:
                oversized_images.append(Path(path).name)

        skipped_over_limit = []
        if len(accepted_image_paths) > WECOM_REPLY_IMAGE_MAX_COUNT:
            skipped_over_limit = [
                Path(path).name
                for path in accepted_image_paths[WECOM_REPLY_IMAGE_MAX_COUNT:]
            ]
            accepted_image_paths = accepted_image_paths[:WECOM_REPLY_IMAGE_MAX_COUNT]

        if accepted_image_paths:
            pending_paths = metadata.setdefault("_wecom_pending_media_paths", [])
            pending_paths.extend(accepted_image_paths)
            pending_text = str(message or "").strip()
            if pending_text:
                metadata["_wecom_pending_media_text"] = pending_text

        messages: List[str] = []
        if accepted_image_paths:
            if len(accepted_image_paths) == 1:
                messages.append(f"已加入当前回复图片: {Path(accepted_image_paths[0]).name}")
            else:
                messages.append(f"已加入当前回复图片 {len(accepted_image_paths)} 张")

        if file_paths:
            messages.append(
                "企业微信长连接暂不支持回传文件，已跳过: "
                + ", ".join(Path(path).name for path in file_paths)
            )

        if oversized_images:
            messages.append(
                "以下图片超过企业微信长连接 10MB 限制，已跳过: "
                + ", ".join(oversized_images)
            )

        if skipped_over_limit:
            messages.append(
                f"企业微信长连接单次最多附带 {WECOM_REPLY_IMAGE_MAX_COUNT} 张图片，已跳过: "
                + ", ".join(skipped_over_limit)
            )

        if invalid_files:
            messages.append(f"跳过 {len(invalid_files)} 个无效文件: {', '.join(invalid_files)}")

        return "\n".join(messages) if messages else "没有可发送的图片"
