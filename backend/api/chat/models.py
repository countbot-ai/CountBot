"""Chat API 的请求/响应模型。"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    """发送消息请求"""

    session_id: str = Field(..., description="会话 ID")
    message: str = Field(default="", description="用户消息内容")
    attachments: Optional[List[str]] = Field(None, description="附件路径列表（可选）")


class PreviewRequest(BaseModel):
    """请求预览请求"""

    session_id: str = Field(..., description="会话 ID")
    message: str = Field(default="", description="拟发送的用户消息内容")
    attachments: Optional[List[str]] = Field(None, description="附件路径列表（可选）")
    channel: Optional[str] = Field(None, description="渠道标识（可选，默认 web-chat）")


class AttachmentItemResponse(BaseModel):
    """附件响应"""
    path: str
    name: str
    size: int
    content_type: Optional[str] = None
    kind: str


class UpdateSessionSummaryRequest(BaseModel):
    """更新会话总结请求"""
    
    summary: str = Field(..., min_length=10, max_length=200, description="会话总结（10-200字符）")


class SummarizeSessionResponse(BaseModel):
    """总结会话响应"""
    
    success: bool = Field(..., description="是否成功")
    summary: str = Field(..., description="生成的总结")
    message: Optional[str] = Field(None, description="消息")


class SendMessageResponse(BaseModel):
    """发送消息响应"""

    message_id: str = Field(..., description="消息 ID")
    streaming: bool = Field(True, description="是否为流式响应")


class SessionResponse(BaseModel):
    """会话响应"""

    id: str
    name: str
    created_at: str
    updated_at: str
    summary: Optional[str] = None
    summary_updated_at: Optional[str] = None


class ToolCallResponse(BaseModel):
    """工具调用响应"""
    
    id: str
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[str] = None
    error: Optional[str] = None
    status: str = "success"
    duration: Optional[int] = None
    spawn_task: Optional[Dict[str, Any]] = None  # 子代理任务详情（仅 spawn 工具调用）
    detail_available: bool = False
    detail_loaded: bool = True
    result_truncated: bool = False
    error_truncated: bool = False


class MessageResponse(BaseModel):
    """消息响应"""

    id: int
    session_id: str
    role: str
    content: str
    reasoning_content: Optional[str] = None
    attachment_items: List[AttachmentItemResponse] = Field(default_factory=list)
    created_at: str
    tool_call_count: int = 0
    special_tool_call_names: List[str] = Field(default_factory=list)
    tool_calls: List[ToolCallResponse] = Field(default_factory=list, description="工具调用记录")


class MessageToolCallPageResponse(BaseModel):
    """单条消息的工具调用分页响应"""

    message_id: int
    total: int
    offset: int
    limit: int
    has_more: bool
    items: List[ToolCallResponse] = Field(default_factory=list)

class UpdateSessionRequest(BaseModel):
    """更新会话请求"""
    name: str

class SessionConfigRequest(BaseModel):
    """会话配置请求"""
    model: Optional[Dict[str, Any]] = Field(None, alias='model_config')
    persona: Optional[Dict[str, Any]] = Field(None, alias='persona_config')
    
    class Config:
        populate_by_name = True


class SessionConfigResponse(BaseModel):
    """会话配置响应"""
    session_id: str
    use_custom_config: bool
    model: Dict[str, Any] = Field(..., alias='model_config')
    persona: Dict[str, Any] = Field(..., alias='persona_config')
    global_defaults: Dict[str, Any]
    
    class Config:
        populate_by_name = True
