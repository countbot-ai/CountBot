"""发送媒体文件工具"""

from pathlib import Path
from typing import Any
from loguru import logger

from backend.modules.tools.base import Tool


IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}

FILE_EXTENSIONS = {
    '.txt', '.pdf', '.doc', '.docx', '.xls', '.xlsx', 
    '.ppt', '.pptx', '.zip', '.rar', '.7z',
    '.mp3', '.mp4', '.avi', '.mov',
    '.json', '.xml', '.csv', '.md'
}


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
- 仅支持频道会话（飞书/QQ/钉钉）
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
    
    def _is_image_file(self, file_path: Path) -> bool:
        """判断是否为图片文件"""
        return file_path.suffix.lower() in IMAGE_EXTENSIONS
    
    def _is_supported_file(self, file_path: Path) -> bool:
        """判断是否为支持的文件格式"""
        ext = file_path.suffix.lower()
        return ext in IMAGE_EXTENSIONS or ext in FILE_EXTENSIONS

    async def _upload_to_oss_if_needed(self, file_path: Path, channel: str) -> str | None:
        """根据频道类型处理文件路径
        
        QQ 需要公网 URL，上传到 OSS
        其他频道使用本地文件路径
        """
        if channel != 'qq':
            return str(file_path)

        try:
            from backend.modules.tools.image_uploader import get_upload_manager

            manager = get_upload_manager()
            url = await manager.upload(file_path)

            if url:
                logger.info(f"文件已上传到 OSS: {url}")
                return url
            else:
                logger.error(f"OSS 上传失败: {file_path}")
                return None

        except Exception as e:
            logger.error(f"OSS 上传异常: {e}")
            return None

    
    async def _parse_session_info(self) -> tuple[str, str] | None:
        """从会话名称解析频道和聊天 ID
        
        会话名称格式:
        - 频道会话: {channel}:{chat_id} 或 {channel}:{chat_id}:{timestamp}
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
                
                parts = session.name.split(':', 2)
                if len(parts) >= 2:
                    channel = parts[0]
                    chat_id = parts[1]
                    
                    valid_channels = {'feishu', 'qq', 'dingtalk', 'telegram', 'discord', 'wechat'}
                    if channel not in valid_channels:
                        logger.warning(f"Invalid channel: {channel}")
                        return None
                    
                    logger.info(f"Parsed session '{session.name}' -> channel='{channel}', chat_id='{chat_id}'")
                    return (channel, chat_id)
                
                logger.warning(f"Invalid session name format: {session.name}")
                return None
                
        except Exception as e:
            logger.error(f"Error parsing session info: {e}")
            return None
    
    async def execute(self, file_paths: list[str], message: str = "") -> str:
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
                    "- 未连接到支持的频道（飞书/QQ/钉钉）\n\n"
                    "请在频道会话中使用此功能"
                )
            
            channel, chat_id = session_info
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
                
                processed_path = await self._upload_to_oss_if_needed(file_path, channel)
                if not processed_path:
                    invalid_files.append(f"{path} (上传失败)")
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
                metadata={}
            )
            
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
