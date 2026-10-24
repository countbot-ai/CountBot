"""Settings API 的请求/响应模型。"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ExternalCodingProfilePayload(BaseModel):
    """外部编码工具 profile 配置。"""

    name: str = Field(..., min_length=1)
    aliases: List[str] = Field(default_factory=list)
    type: str = "cli"
    icon_svg: str = ""
    enabled: bool = False
    description: str = ""
    command: str = ""
    args: List[str] = Field(default_factory=list)
    working_dir: str = ""
    stdin_template: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)
    inherit_env: List[str] = Field(default_factory=list)
    session_mode: str = "history"
    history_message_count: int = Field(default=10, ge=1, le=50)
    timeout: Optional[int] = None
    success_exit_codes: List[int] = Field(default_factory=lambda: [0])


class ExternalCodingToolsConfigPayload(BaseModel):
    """外部编码工具完整配置。"""

    version: int = 1
    profiles: List[ExternalCodingProfilePayload] = Field(default_factory=list)


class ExternalCodingToolsConfigResponse(ExternalCodingToolsConfigPayload):
    """外部编码工具配置响应。"""

    config_path: str


class ExternalCodingProfileCheckRequest(BaseModel):
    """外部编码工具 profile 检查请求。"""

    profile: ExternalCodingProfilePayload


class ExternalCodingProfileCheckResponse(BaseModel):
    """外部编码工具 profile 检查结果。"""

    success: bool
    message: str
    resolved_command: Optional[str] = None
    missing_env: List[str] = Field(default_factory=list)

class ProviderMetadataResponse(BaseModel):
    """Provider 元数据响应"""
    
    id: str = Field(..., description="Provider ID")
    name: str = Field(..., description="显示名称")
    default_api_base: Optional[str] = Field(None, description="默认 API 基础 URL")
    default_model: Optional[str] = Field(None, description="默认模型名称")
    enabled: bool = Field(False, description="是否已启用")
    configured: bool = Field(False, description="配置是否完整")
    selectable: bool = Field(False, description="是否可用于实际请求")
    requires_api_key: bool = Field(True, description="是否要求 API Key")
    requires_api_base: bool = Field(False, description="是否要求自定义 API Base")
    status: str = Field("disabled", description="运行状态")
    reason: str = Field("disabled", description="状态原因")
    provider_group: str = Field("experimental", description="前端展示分组")
    thinking_control_tier: str = Field("unsupported", description="思考开关支持等级")


class ProviderConfigResponse(BaseModel):
    """Provider 配置响应"""
    
    enabled: bool = Field(..., description="是否启用")
    api_key: Optional[str] = Field(None, description="API 密钥（脱敏）")
    api_keys: List[str] = Field(default_factory=list, description="API 密钥列表")
    api_base: Optional[str] = Field(None, description="API 基础 URL")


class ModelConfigResponse(BaseModel):
    """模型配置响应"""
    
    provider: str = Field(..., description="Provider 名称")
    model: str = Field(..., description="模型名称")
    api_mode: str = Field(..., description="OpenAI API 模式，固定为 chat.completions")
    temperature: float = Field(..., description="温度参数，0 表示不发送")
    max_tokens: int = Field(..., description="最大 token 数")
    max_iterations: int = Field(..., description="最大迭代次数")
    thinking_enabled: bool = Field(..., description="是否启用思考模式")
    supports_image: Optional[bool] = Field(
        None,
        description="图片输入能力：None=自动判断，True=强制开启，False=关闭",
    )


class WorkspaceConfigResponse(BaseModel):
    """工作空间配置响应"""

    path: str = Field(..., description="工作空间路径")


class SecurityConfigResponse(BaseModel):
    """安全配置响应"""
    
    # 危险命令检测
    dangerous_commands_blocked: bool = Field(..., description="是否阻止危险命令")
    custom_deny_patterns: List[str] = Field(..., description="自定义拒绝模式列表")
    
    # 命令白名单
    command_whitelist_enabled: bool = Field(..., description="是否启用命令白名单")
    custom_allow_patterns: List[str] = Field(..., description="自定义允许模式列表")
    
    # 审计日志
    audit_log_enabled: bool = Field(..., description="是否启用审计日志")
    
    # 其他安全选项
    command_timeout: int = Field(..., description="命令超时时间（秒）")
    subagent_timeout: int = Field(..., description="子代理超时时间（秒）")
    max_output_length: int = Field(..., description="最大输出长度")
    restrict_to_workspace: bool = Field(..., description="是否限制在工作空间内")


class HeartbeatConfigResponse(BaseModel):
    """主动问候配置响应"""
    enabled: bool = Field(..., description="是否启用")
    channel: str = Field(..., description="推送渠道")
    account_id: str = Field(default="default", description="推送机器人账号 ID")
    chat_id: str = Field(..., description="推送目标 ID")
    schedule: str = Field(..., description="检查频率 cron 表达式")
    idle_threshold_hours: int = Field(..., description="空闲阈值（小时）")
    quiet_start: int = Field(..., description="免打扰开始时间")
    quiet_end: int = Field(..., description="免打扰结束时间")
    max_greets_per_day: int = Field(..., description="每天最多问候次数")


class PersonaConfigResponse(BaseModel):
    """用户信息和AI人设配置响应"""
    
    ai_name: str = Field(..., description="AI的名字")
    user_name: str = Field(..., description="用户的称呼")
    user_address: str = Field(default="", description="用户的常用地址")
    output_language: str = Field(default="中文", description="AI默认输出语言")
    personality: str = Field(..., description="AI的性格类型")
    custom_personality: str = Field(..., description="自定义性格描述")
    max_history_messages: int = Field(
        ...,
        description="最大对话历史条数，0 表示不限且关闭短期上下文总结",
    )
    enable_short_context_summary: bool = Field(
        default=False,
        description="是否启用短期上下文摘要缓存，默认关闭",
    )
    heartbeat: HeartbeatConfigResponse = Field(..., description="主动问候配置")


class InjectionConfigResponse(BaseModel):
    """上下文注入开关响应"""

    core_rules: bool = Field(..., description="核心规则段（CountBot规则/工具执行/文件技能/记忆/知识库/安全）")
    external_coding_guidance: bool = Field(..., description="外部编码代理指引")
    skills_always: bool = Field(..., description="always=true 技能全文注入")
    skills_summary: bool = Field(..., description="已启用技能摘要注入")
    agent_teams: bool = Field(..., description="已激活多智能体团队区块")
    dynamic_context: bool = Field(..., description="首条 user 消息动态上下文（时间/用户资料/会话摘要/渠道）")
    team_reminder: bool = Field(..., description="@团队强制提醒")
    disabled_tools: List[str] = Field(default_factory=list, description="禁用的工具名列表")
    auto_memory_summary: bool = Field(..., description="后台自动记忆维护（溢出总结/整会话沉淀）")


class SettingsResponse(BaseModel):
    """设置响应"""
    
    providers: Dict[str, ProviderConfigResponse] = Field(..., description="Provider 配置")
    model: ModelConfigResponse = Field(..., description="模型配置")
    workspace: WorkspaceConfigResponse = Field(..., description="工作空间配置")
    security: SecurityConfigResponse = Field(..., description="安全配置")
    persona: PersonaConfigResponse = Field(..., description="用户信息和AI人设配置")
    injection: Optional[InjectionConfigResponse] = Field(None, description="上下文注入开关")
    workspace_migration: Optional[dict] = Field(None, description="工作区迁移提示信息")


class UpdateSettingsRequest(BaseModel):
    """更新设置请求"""
    
    providers: Optional[Dict[str, dict]] = Field(None, description="Provider 配置")
    model: Optional[dict] = Field(None, description="模型配置")
    workspace: Optional[dict] = Field(None, description="工作空间配置")
    security: Optional[dict] = Field(None, description="安全配置")
    persona: Optional[dict] = Field(None, description="用户信息和AI人设配置")
    injection: Optional[dict] = Field(None, description="上下文注入开关")


class TestConnectionRequest(BaseModel):
    """测试连接请求"""
    
    provider: str = Field(..., description="Provider 名称")
    api_key: str = Field(default="", description="API 密钥")
    api_base: Optional[str] = Field(None, description="API 基础 URL")
    model: Optional[str] = Field(None, description="模型名称（可选）")
    api_mode: Optional[str] = Field(None, description="API 模式（仅保留兼容字段）")
    temperature: Optional[float] = Field(None, description="温度参数（可选，0 表示不发送）")
    max_tokens: Optional[int] = Field(None, description="最大 token 数（可选，0 表示不发送）")
    thinking_enabled: Optional[bool] = Field(None, description="是否启用思考模式（可选）")


class TestConnectionResponse(BaseModel):
    """测试连接响应"""
    
    success: bool = Field(..., description="是否成功")
    message: Optional[str] = Field(None, description="消息")
    error: Optional[str] = Field(None, description="错误信息")

class ImportSettingsRequest(BaseModel):
    """导入配置请求"""
    
    version: str = Field(..., description="配置文件版本")
    config: dict = Field(..., description="配置数据")
    merge: bool = Field(default=False, description="是否合并现有配置")
    sections: Optional[List[str]] = Field(None, description="要导入的配置节")
