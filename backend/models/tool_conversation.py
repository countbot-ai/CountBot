"""工具调用对话历史数据模型"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, Index

from backend.database import Base


class ToolConversation(Base):
    """工具调用对话记录表"""
    
    __tablename__ = "tool_conversations"
    
    id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    message_id = Column(Integer, nullable=True, index=True)  # 关联的消息ID
    timestamp = Column(String, nullable=False, index=True)
    tool_name = Column(String, nullable=False, index=True)
    arguments = Column(Text, nullable=False)  # JSON string
    user_message = Column(Text, nullable=True)
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    outcome_projection = Column(Text, nullable=True)  # 新增可空列；旧行保留 NULL
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        """转换为字典"""
        import json
        from backend.modules.tools.outcome_projection import projection_state, read_stored_projection
        
        return {
            "id": self.id,
            "session_id": self.session_id,
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "tool_name": self.tool_name,
            "arguments": json.loads(self.arguments) if self.arguments else {},
            "user_message": self.user_message,
            "result": self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "outcome_projection": read_stored_projection(self.outcome_projection),
            "outcome_projection_state": projection_state(self.outcome_projection).value,
        }
