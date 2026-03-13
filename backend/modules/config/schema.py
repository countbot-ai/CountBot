"""配置数据模型"""

from typing import Optional

from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    """LLM 提供商配置"""
    api_key: str = ""
    api_base: Optional[str] = None
    enabled: bool = False
    model: Optional[str] = None


class ModelConfig(BaseModel):
    """模型配置"""
    provider: str = "zhipu"
    model: str = "glm-5"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=0, ge=0, le=100000)
    max_iterations: int = Field(default=25, ge=1, le=150)


class WorkspaceConfig(BaseModel):
    """工作空间配置"""
    path: str = ""
    
    def __init__(self, **data):
        """初始化，设置默认工作空间路径"""
        super().__init__(**data)
        if not self.path:
            self.path = self._get_default_workspace_path()
    
    def _get_default_workspace_path(self) -> str:
        """获取默认工作空间路径"""
        import os
        import sys
        from pathlib import Path
        
        try:
            # 获取程序目录
            if getattr(sys, 'frozen', False):
                # 打包后的可执行文件
                app_dir = Path(sys.executable).parent
            else:
                # 开发环境
                app_dir = Path(__file__).parent.parent.parent.parent
            
            # 默认工作空间：程序目录/workspace
            default_workspace = app_dir / "workspace"
            default_workspace.mkdir(exist_ok=True)
            
            # 创建临时目录
            temp_dir = default_workspace / "temp"
            temp_dir.mkdir(exist_ok=True)
            
            return str(default_workspace.resolve())
            
        except Exception:
            # 备用方案：当前目录/workspace
            fallback_workspace = Path.cwd() / "workspace"
            fallback_workspace.mkdir(exist_ok=True)
            (fallback_workspace / "temp").mkdir(exist_ok=True)
            return str(fallback_workspace.resolve())


class HeartbeatConfig(BaseModel):
    """主动问候配置"""
    enabled: bool = Field(default=False, description="是否启用主动问候")
    channel: str = Field(default="", description="推送渠道（feishu/telegram/dingtalk/wecom/qq）")
    chat_id: str = Field(default="", description="推送目标 ID（群组或用户）")
    schedule: str = Field(default="0 * * * *", description="检查频率 cron 表达式")
    idle_threshold_hours: int = Field(default=4, ge=1, le=24, description="用户空闲多少小时后触发")
    quiet_start: int = Field(default=21, ge=0, le=23, description="免打扰开始时间（小时，北京时间）")
    quiet_end: int = Field(default=8, ge=0, le=23, description="免打扰结束时间（小时，北京时间）")
    max_greets_per_day: int = Field(default=2, ge=1, le=5, description="每天最多问候次数")


class PersonaConfig(BaseModel):
    """用户信息和AI人设配置"""
    ai_name: str = Field(default="小C", description="AI的名字")
    user_name: str = Field(default="主人", description="用户的称呼")
    user_address: str = Field(default="", description="用户的常用地址（可选）")
    output_language: str = Field(default="中文", description="AI默认输出语言")
    personality: str = Field(default="grumpy", description="AI的性格类型")
    custom_personality: str = Field(default="", description="自定义性格描述")
    max_history_messages: int = Field(default=100, ge=-1, le=500, description="最大对话历史条数，-1表示不限")
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig, description="主动问候配置")


class SecurityConfig(BaseModel):
    """安全配置"""
    # 危险命令检测
    dangerous_commands_blocked: bool = Field(default=True, description="是否阻止危险命令")
    custom_deny_patterns: list[str] = Field(default_factory=list, description="自定义拒绝模式列表")
    
    # 命令白名单
    command_whitelist_enabled: bool = Field(default=False, description="是否启用命令白名单")
    custom_allow_patterns: list[str] = Field(default_factory=list, description="自定义允许模式列表")
    
    # 审计日志
    audit_log_enabled: bool = Field(default=True, description="是否启用审计日志")
    
    # 超时配置
    command_timeout: int = Field(default=300, ge=10, le=1800, description="工具调用超时时间（秒）")
    subagent_timeout: int = Field(default=600, ge=60, le=3600, description="子代理超时时间（秒）")
    
    # 输出限制
    max_output_length: int = Field(default=10000, ge=100, le=1000000, description="最大输出长度（字符）")
    
    # 工作空间限制
    restrict_to_workspace: bool = Field(default=False, description="是否限制命令在工作空间内执行")


class TelegramConfig(BaseModel):
    """Telegram 渠道配置"""
    enabled: bool = False
    token: str = ""
    proxy: Optional[str] = None
    allow_from: list[str] = Field(default_factory=list)


class DiscordConfig(BaseModel):
    """Discord 渠道配置"""
    enabled: bool = False
    token: str = ""
    allow_from: list[str] = Field(default_factory=list)


class TencentOSSConfig(BaseModel):
    """腾讯云 OSS 配置（可选）"""
    secret_id: str = ""
    secret_key: str = ""
    bucket: str = ""
    region: str = "ap-guangzhou"


class QQConfig(BaseModel):
    """QQ 渠道配置"""
    enabled: bool = False
    app_id: str = ""
    secret: str = ""
    allow_from: list[str] = Field(default_factory=list)
    markdown_enabled: bool = True
    group_markdown_enabled: bool = True
    oss: Optional[TencentOSSConfig] = Field(default_factory=TencentOSSConfig)





class DingTalkConfig(BaseModel):
    """钉钉渠道配置"""
    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    allow_from: list[str] = Field(default_factory=list)


class FeishuConfig(BaseModel):
    """飞书渠道配置"""
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    encrypt_key: str = ""
    verification_token: str = ""
    allow_from: list[str] = Field(default_factory=list)


class WeiboConfig(BaseModel):
    """微博渠道配置"""
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    account_id: str = Field(default="default", description="账号 ID，用于多账号支持")
    token_endpoint: str = Field(default="http://open-im.api.weibo.com/open/auth/ws_token")
    ws_endpoint: str = Field(default="ws://open-im.api.weibo.com/ws/stream")
    allow_from: list[str] = Field(default_factory=list)


class WeComConfig(BaseModel):
    """企业微信渠道配置"""
    enabled: bool = False
    bot_id: str = ""
    secret: str = ""
    websocket_url: str = Field(default="wss://openws.work.weixin.qq.com", description="WebSocket 连接地址")
    allow_from: list[str] = Field(default_factory=list)


class XiaozhiConfig(BaseModel):
    """小智AI渠道配置（MCP Client 模式）"""
    enabled: bool = False
    endpoint: str = Field(default="", description="小智AI MCP WebSocket 接入点，如 ws://192.168.1.x:8765")
    enable_conversation: bool = Field(default=False, description="启用对话模式（通过 send_message 工具接收用户消息）")
    allow_from: list[str] = Field(default_factory=list)


class ChannelsConfig(BaseModel):
    """渠道配置"""
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    qq: QQConfig = Field(default_factory=QQConfig)
    dingtalk: DingTalkConfig = Field(default_factory=DingTalkConfig)
    feishu: FeishuConfig = Field(default_factory=FeishuConfig)
    weibo: WeiboConfig = Field(default_factory=WeiboConfig)
    wecom: WeComConfig = Field(default_factory=WeComConfig)
    xiaozhi: XiaozhiConfig = Field(default_factory=XiaozhiConfig)


class AppConfig(BaseModel):
    """应用配置"""
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    model: ModelConfig = Field(default_factory=ModelConfig)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    persona: PersonaConfig = Field(default_factory=PersonaConfig)
    theme: str = "auto"
    language: str = "auto"
    font_size: str = "medium"
    
    def __init__(self, **data):
        """初始化配置"""
        super().__init__(**data)
        
        from backend.modules.providers.registry import get_provider_ids, get_provider_metadata
        
        for provider_id in get_provider_ids():
            if provider_id not in self.providers:
                metadata = get_provider_metadata(provider_id)
                
                if provider_id == "zhipu":
                    self.providers[provider_id] = ProviderConfig(
                        api_key="",
                        api_base="https://open.bigmodel.cn/api/paas/v4",
                        enabled=True
                    )
                else:
                    self.providers[provider_id] = ProviderConfig(
                        api_base=metadata.default_api_base if metadata else None
                    )
