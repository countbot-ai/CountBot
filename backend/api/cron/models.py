"""Cron API 的请求/响应模型。"""

from typing import List, Optional, Union
from datetime import datetime
from pydantic import BaseModel, Field


class CronJobInfo(BaseModel):
    """Cron 任务信息"""
    
    id: str = Field(..., description="任务 ID")
    name: str = Field(..., description="任务名称")
    schedule: str = Field(..., description="Cron 表达式")
    message: str = Field(..., description="要执行的消息")
    enabled: bool = Field(..., description="是否启用")
    channel: Optional[str] = Field(None, description="渠道名称")
    account_id: Optional[str] = Field(None, description="机器人账号 ID")
    chat_id: Optional[str] = Field(None, description="聊天 ID")
    deliver_response: bool = Field(False, description="是否发送响应到渠道")
    last_run: Optional[str] = Field(None, description="上次运行时间")
    next_run: Optional[str] = Field(None, description="下次运行时间")
    last_status: Optional[str] = Field(None, description="上次执行状态")
    last_error: Optional[str] = Field(None, description="上次错误信息")
    run_count: int = Field(0, description="执行次数")
    error_count: int = Field(0, description="错误次数")
    created_at: str = Field(..., description="创建时间")
    max_retries: int = Field(0, description="最大重试次数")
    retry_delay: int = Field(60, description="重试延迟（秒）")
    delete_on_success: bool = Field(False, description="成功后自动删除")


class ListCronJobsResponse(BaseModel):
    """Cron 任务列表响应"""
    
    jobs: List[CronJobInfo] = Field(..., description="任务列表")


class CreateCronJobRequest(BaseModel):
    """创建 Cron 任务请求"""
    
    name: str = Field(..., description="任务名称")
    schedule: str = Field(..., description="Cron 表达式")
    message: str = Field(..., description="要执行的消息")
    enabled: bool = Field(True, description="是否启用")
    channel: Optional[str] = Field(None, description="渠道名称")
    account_id: Optional[str] = Field(None, description="机器人账号 ID")
    chat_id: Optional[str] = Field(None, description="聊天 ID")
    deliver_response: bool = Field(False, description="是否发送响应到渠道")
    max_retries: int = Field(0, description="最大重试次数（0=不重试）")
    retry_delay: int = Field(60, description="重试延迟（秒）")
    delete_on_success: bool = Field(False, description="成功后自动删除")


class UpdateCronJobRequest(BaseModel):
    """更新 Cron 任务请求"""
    
    name: Optional[str] = Field(None, description="任务名称")
    schedule: Optional[str] = Field(None, description="Cron 表达式")
    message: Optional[str] = Field(None, description="要执行的消息")
    enabled: Optional[bool] = Field(None, description="是否启用")
    channel: Optional[str] = Field(None, description="渠道名称")
    account_id: Optional[str] = Field(None, description="机器人账号 ID")
    chat_id: Optional[str] = Field(None, description="聊天 ID")
    deliver_response: Optional[bool] = Field(None, description="是否发送响应到渠道")
    max_retries: Optional[int] = Field(None, description="最大重试次数")
    retry_delay: Optional[int] = Field(None, description="重试延迟（秒）")
    delete_on_success: Optional[bool] = Field(None, description="成功后自动删除")


class CronJobResponse(BaseModel):
    """Cron 任务响应"""
    
    job: CronJobInfo = Field(..., description="任务信息")


class DeleteCronJobResponse(BaseModel):
    """删除 Cron 任务响应"""
    
    success: bool = Field(..., description="是否成功")


class ExecuteCronJobResponse(BaseModel):
    """执行 Cron 任务响应"""
    
    success: bool = Field(..., description="是否成功")
    message: Optional[str] = Field(None, description="消息")


class ValidateCronRequest(BaseModel):
    """验证 Cron 表达式请求"""
    
    schedule: str = Field(..., description="Cron 表达式")


class ValidateCronResponse(BaseModel):
    """验证 Cron 表达式响应"""
    
    valid: bool = Field(..., description="是否有效")
    description: Optional[str] = Field(None, description="表达式描述")
    next_run: Optional[str] = Field(None, description="下次运行时间")


class BatchCreateCronJobsRequest(BaseModel):
    """批量创建 Cron 任务请求"""
    
    jobs: List[CreateCronJobRequest] = Field(..., description="任务列表")


class BatchCreateCronJobsResponse(BaseModel):
    """批量创建 Cron 任务响应"""
    
    success_count: int = Field(..., description="成功创建数量")
    failed_count: int = Field(..., description="失败数量")
    jobs: List[CronJobInfo] = Field(..., description="成功创建的任务")
    errors: List[dict] = Field(..., description="失败的任务及错误信息")


class BatchDeleteCronJobsRequest(BaseModel):
    """批量删除 Cron 任务请求"""
    
    job_ids: List[str] = Field(..., description="任务 ID 列表")


class BatchDeleteCronJobsResponse(BaseModel):
    """批量删除 Cron 任务响应"""
    
    success_count: int = Field(..., description="成功删除数量")
    failed_count: int = Field(..., description="失败数量")
    deleted_ids: List[str] = Field(..., description="成功删除的任务 ID")
    errors: List[dict] = Field(..., description="失败的任务及错误信息")


class CronJobDetailResponse(BaseModel):
    """Cron 任务详细信息响应"""
    
    job: CronJobInfo = Field(..., description="任务信息")
    last_response: Optional[str] = Field(None, description="完整的上次响应")
    last_error: Optional[str] = Field(None, description="完整的上次错误")


class CronSessionMessage(BaseModel):
    """Cron 任务关联会话的消息"""

    role: str = Field(..., description="消息角色")
    content: str = Field(..., description="消息内容")
    created_at: str = Field(..., description="消息创建时间")


class CronJobMessagesResponse(BaseModel):
    """Cron 任务关联会话消息响应"""

    job_id: str = Field(..., description="任务 ID")
    job_name: str = Field(..., description="任务名称")
    session_id: Optional[str] = Field(None, description="会话 ID")
    session_name: Optional[str] = Field(None, description="会话名称")
    messages: List[CronSessionMessage] = Field(default_factory=list, description="消息列表")


class CleanupCronSessionRequest(BaseModel):
    """清理 Cron 任务会话请求"""

    keep: int = Field(10, description="保留最近消息条数", ge=0)


class CleanupCronSessionResponse(BaseModel):
    """清理 Cron 任务会话响应"""

    success: bool = Field(..., description="是否成功")
    job_id: str = Field(..., description="任务 ID")
    job_name: str = Field(..., description="任务名称")
    session_id: Optional[str] = Field(None, description="会话 ID")
    session_name: Optional[str] = Field(None, description="会话名称")
    deleted_count: int = Field(0, description="删除消息数")
    kept_count: int = Field(0, description="保留消息数")


class ResetCronSessionResponse(BaseModel):
    """重置 Cron 任务会话响应"""

    success: bool = Field(..., description="是否成功")
    job_id: str = Field(..., description="任务 ID")
    job_name: str = Field(..., description="任务名称")
    session_id: Optional[str] = Field(None, description="会话 ID")
    session_name: Optional[str] = Field(None, description="会话名称")
    deleted_message_count: int = Field(0, description="删除消息数")
