"""配置数据模型"""

from typing import ClassVar, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ProviderConfig(BaseModel):
    """LLM 提供商配置"""
    api_key: str = ""
    api_base: Optional[str] = None
    enabled: bool = True
    model: Optional[str] = None


class ModelConfig(BaseModel):
    """模型配置"""
    MAX_TOKENS_LIMIT: ClassVar[int] = 2_000_000

    provider: str = "zhipu"
    model: str = "glm-5"
    api_mode: Literal["chat_completions"] = Field(
        default="chat_completions",
        description="OpenAI API 模式，固定为 chat.completions",
    )
    temperature: float = Field(default=0.0, ge=0.0, le=2.0, description="温度参数，0 表示不发送")
    max_tokens: int = Field(
        default=0,
        ge=0,
        le=MAX_TOKENS_LIMIT,
        description="最大输出 token 数，0 表示不发送",
    )
    max_iterations: int = Field(default=25, ge=1, le=150)
    thinking_enabled: bool = Field(default=True, description="是否启用模型思考模式")

    @field_validator("api_mode", mode="before")
    @classmethod
    def normalize_api_mode(cls, value):
        return "chat_completions"


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
    account_id: str = Field(default="default", description="推送机器人账号 ID（多机器人渠道）")
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
    max_history_messages: int = Field(
        default=0,
        ge=-1,
        le=500,
        description="最大对话历史条数，0表示不限且关闭短期上下文总结，-1为旧版兼容的不限制",
    )
    enable_short_context_summary: bool = Field(
        default=False,
        description="是否启用短期上下文摘要缓存；默认关闭，关闭后即使限制历史条数，也只发送最近窗口原始消息",
    )
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig, description="主动问候配置")


class SecurityConfig(BaseModel):
    """安全配置"""
    # 危险命令检测
    dangerous_commands_blocked: bool = Field(default=True, description="是否阻止危险命令")
    custom_deny_patterns: List[str] = Field(default_factory=list, description="自定义拒绝模式列表")
    
    # 命令白名单
    command_whitelist_enabled: bool = Field(default=False, description="是否启用命令白名单")
    custom_allow_patterns: List[str] = Field(default_factory=list, description="自定义允许模式列表")
    
    # 审计日志
    audit_log_enabled: bool = Field(default=True, description="是否启用审计日志")
    
    # 超时配置
    command_timeout: int = Field(default=180, ge=10, le=1800, description="工具调用超时时间（秒）")
    subagent_timeout: int = Field(default=1200, ge=60, le=3600, description="子代理超时时间（秒）")
    
    # 输出限制
    max_output_length: int = Field(default=10000, ge=100, le=1000000, description="最大输出长度（字符）")
    
    # 工作空间限制
    restrict_to_workspace: bool = Field(default=False, description="是否限制命令在工作空间内执行")


class ChannelAccountConfig(BaseModel):
    """支持多机器人实例的基础渠道配置。"""

    enabled: bool = False
    display_name: str = Field(default="", description="机器人名称")
    account_id: str = Field(default="default", description="机器人账号 ID")
    allow_from: List[str] = Field(default_factory=list)
    routing_mode: str = Field(
        default="ai",
        description="默认路由模式：ai=通过 CountBot 主 AI，direct=直接转发给外部编程代理",
    )
    external_coding_profile: str = Field(
        default="",
        description="默认外部编程代理 profile 名称，如 codex、claude",
    )


class TelegramAccountConfig(ChannelAccountConfig):
    """Telegram 机器人配置"""

    token: str = ""
    proxy: Optional[str] = None


class TelegramConfig(TelegramAccountConfig):
    """Telegram 渠道配置"""

    accounts: Dict[str, TelegramAccountConfig] = Field(default_factory=dict)


class DiscordAccountConfig(ChannelAccountConfig):
    """Discord 机器人配置"""

    token: str = ""


class DiscordConfig(DiscordAccountConfig):
    """Discord 渠道配置"""

    accounts: Dict[str, DiscordAccountConfig] = Field(default_factory=dict)


class QQAccountConfig(ChannelAccountConfig):
    """QQ 机器人配置"""

    app_id: str = ""
    secret: str = ""
    markdown_enabled: bool = True
    group_markdown_enabled: bool = True


class QQConfig(QQAccountConfig):
    """QQ 渠道配置"""

    accounts: Dict[str, QQAccountConfig] = Field(default_factory=dict)


class DingTalkAccountConfig(ChannelAccountConfig):
    """钉钉机器人配置"""

    client_id: str = ""
    client_secret: str = ""


class DingTalkConfig(DingTalkAccountConfig):
    """钉钉渠道配置"""

    accounts: Dict[str, DingTalkAccountConfig] = Field(default_factory=dict)


class FeishuAccountConfig(ChannelAccountConfig):
    """飞书机器人配置"""

    app_id: str = ""
    app_secret: str = ""


class FeishuConfig(FeishuAccountConfig):
    """飞书渠道配置"""

    accounts: Dict[str, FeishuAccountConfig] = Field(default_factory=dict)


class WeiboAccountConfig(ChannelAccountConfig):
    """微博机器人配置"""

    app_id: str = ""
    app_secret: str = ""
    account_id: str = Field(default="default", description="账号 ID，用于多账号支持")
    token_endpoint: str = Field(default="http://open-im.api.weibo.com/open/auth/ws_token")
    ws_endpoint: str = Field(default="ws://open-im.api.weibo.com/ws/stream")


class WeiboConfig(WeiboAccountConfig):
    """微博渠道配置"""

    accounts: Dict[str, WeiboAccountConfig] = Field(default_factory=dict)


class WeComAccountConfig(ChannelAccountConfig):
    """企业微信机器人配置"""

    bot_id: str = ""
    secret: str = ""
    websocket_url: str = Field(default="wss://openws.work.weixin.qq.com", description="WebSocket 连接地址")


class WeComConfig(WeComAccountConfig):
    """企业微信渠道配置"""

    accounts: Dict[str, WeComAccountConfig] = Field(default_factory=dict)


class WeChatAccountConfig(ChannelAccountConfig):
    """微信机器人配置"""

    base_url: str = Field(default="https://ilinkai.weixin.qq.com", description="微信 iLink API 地址")
    cdn_base_url: str = Field(default="https://novac2c.cdn.weixin.qq.com/c2c", description="微信 CDN 地址")
    token: str = ""
    login_bot_id: str = Field(default="", description="扫码登录返回的 bot 标识")
    login_user_id: str = Field(default="", description="扫码登录返回的微信用户标识")


class WeChatConfig(WeChatAccountConfig):
    """微信渠道配置"""

    accounts: Dict[str, WeChatAccountConfig] = Field(default_factory=dict)


class XiaozhiAccountConfig(ChannelAccountConfig):
    """小智AI 机器人配置（MCP Client 模式）"""

    endpoint: str = Field(default="", description="小智AI MCP WebSocket 接入点，如 ws://192.168.1.x:8765")
    enable_conversation: bool = Field(default=False, description="启用对话模式（通过 send_message 工具接收用户消息）")


class XiaozhiConfig(XiaozhiAccountConfig):
    """小智AI渠道配置（MCP Client 模式）"""

    accounts: Dict[str, XiaozhiAccountConfig] = Field(default_factory=dict)


class ChannelsConfig(BaseModel):
    """渠道配置"""
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    qq: QQConfig = Field(default_factory=QQConfig)
    wechat: WeChatConfig = Field(default_factory=WeChatConfig)
    dingtalk: DingTalkConfig = Field(default_factory=DingTalkConfig)
    feishu: FeishuConfig = Field(default_factory=FeishuConfig)
    weibo: WeiboConfig = Field(default_factory=WeiboConfig)
    wecom: WeComConfig = Field(default_factory=WeComConfig)
    xiaozhi: XiaozhiConfig = Field(default_factory=XiaozhiConfig)


class AppConfig(BaseModel):
    """应用配置"""
    providers: Dict[str, ProviderConfig] = Field(default_factory=dict)
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
                        api_base=metadata.default_api_base if metadata else None,
                        enabled=True,
                    )
