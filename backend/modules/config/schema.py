"""配置数据模型"""

from typing import ClassVar, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ModelEntry(BaseModel):
    """供应商下的单个模型条目。

    供应商持有模型清单，全局 ModelConfig 只记录「当前选中哪一个」。
    """

    id: str = Field(..., description="模型 ID（供应商内唯一）")
    display_name: Optional[str] = Field(None, description="展示名称，空则用 id")
    enabled: bool = Field(True, description="是否在模型选择器中可见可选")
    context_window: Optional[int] = Field(
        None, description="上下文窗口（token）：决定压缩触发阈值，未填时用兜底值"
    )
    supports_image: Optional[bool] = Field(
        None,
        description="图片输入能力：None=按模型名自动判断，True=强制开启，False=关闭",
    )
    reasoning_levels: List[str] = Field(
        default_factory=list,
        description=(
            "该模型可选的思考档位（从低到高）。空=用内置建议档位；"
            "用户可自由增删，自定义模型同样可填"
        ),
    )
    reasoning_level: Optional[str] = Field(
        None,
        description="默认思考档位；空=取档位列表首项或不下发档位（沿用旧行为）",
    )
    source: Literal["builtin", "manual", "fetched"] = Field(
        "manual",
        description="来源：内置预设 / 手工填写 / 从上游 /models 拉取",
    )


class ProviderConfig(BaseModel):
    """LLM 提供商配置"""
    api_key: str = ""
    api_keys: List[str] = Field(default_factory=list, description="API 密钥列表，用于轮换")
    api_base: Optional[str] = None
    enabled: bool = True
    name: Optional[str] = Field(None, description="自定义展示名，空则用注册表名称")
    api_type: Literal[
        "openai-chat-completions",
        "openai-responses",
        "anthropic-messages",
    ] = Field(
        "openai-chat-completions",
        description="供应商协议：chat.completions / Responses / Anthropic Messages",
    )
    models: List[ModelEntry] = Field(
        default_factory=list,
        description="该供应商下的模型清单",
    )
    model: Optional[str] = Field(
        None,
        description="历史字段：改造前保存的单个模型名，仅用于迁移与读兼容",
    )

    def get_effective_api_keys(self) -> List[str]:
        """返回去重后的有效 API Key 列表，保证至少包含 api_key。"""
        seen: set[str] = set()
        result: List[str] = []
        for key in self.api_keys:
            trimmed = (key or "").strip()
            if trimmed and trimmed not in seen:
                seen.add(trimmed)
                result.append(trimmed)
        primary = (self.api_key or "").strip()
        if primary and primary not in seen:
            result.insert(0, primary)
        return result

    def get_model_ids(self, *, include_disabled: bool = False) -> List[str]:
        """按清单顺序返回模型 ID。"""
        return [
            entry.id
            for entry in self.models
            if entry.id and (include_disabled or entry.enabled)
        ]

    def find_model(self, model_id: Optional[str]) -> Optional[ModelEntry]:
        """按 ID 查找模型条目。"""
        target = (model_id or "").strip()
        if not target:
            return None
        for entry in self.models:
            if entry.id == target:
                return entry
        return None

    def ensure_model(self, model_id: str, *, source: str = "manual") -> ModelEntry:
        """确保某模型在清单中，返回已有或新建的条目（幂等）。"""
        trimmed = (model_id or "").strip()
        existing = self.find_model(trimmed)
        if existing is not None:
            return existing
        entry = ModelEntry(id=trimmed, source=source)  # type: ignore[arg-type]
        self.models.append(entry)
        return entry


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
    reasoning_level: Optional[str] = Field(
        default=None,
        description=(
            "思考档位（none/low/medium/high/xhigh/max/ultra…）；"
            "设置页与模型条目未给时回落到 thinking_enabled 旧行为"
        ),
    )
    supports_image: Optional[bool] = Field(
        default=None,
        description="图片输入能力：None=按模型名自动判断，True=强制按图片输入，False=降级为路径",
    )

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
    channel: str = Field(default="", description="推送渠道（feishu/telegram/dingtalk/wecom/qq/serverchan）")
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


class CompactionConfig(BaseModel):
    """上下文压缩配置。

    默认值面向「自动压缩在接近窗口上限前介入」：阈值取窗口的一半，尾部保留量按
    窗口比例夹取，使大窗口模型不保留过量原文。
    """

    enabled: bool = Field(default=True, description="是否启用自动上下文压缩")
    threshold_percent: float = Field(
        default=0.5,
        ge=0.05,
        le=1.0,
        description="触发压缩的窗口比例：达到该比例即压缩",
    )
    threshold_tokens: Optional[int] = Field(
        default=None,
        ge=1000,
        description="触发阈值的绝对值上限（token），与窗口比例取较小者",
    )
    target_ratio: float = Field(
        default=0.2,
        ge=0.05,
        le=0.9,
        description="legacy 模式下尾部原文预算占阈值的比例",
    )
    tail_mode: Literal["lean", "legacy"] = Field(
        default="lean",
        description="尾部预算模式：lean 按窗口比例夹取，legacy 按阈值比例计算",
    )
    protect_first_n: int = Field(
        default=3, ge=0, le=20, description="头部额外保护的非系统消息条数"
    )
    protect_last_n: int = Field(
        default=20, ge=1, le=100, description="尾部最少保留的消息条数"
    )
    min_tail_user_messages: int = Field(
        default=1, ge=1, le=10, description="尾部至少保留的用户消息条数"
    )
    message_threshold: int = Field(
        default=15, ge=1, le=500, description="条数兜底阈值：超过该条数也触发压缩"
    )
    max_attempts: int = Field(
        default=3, ge=1, le=10, description="摘要失败后的最大重试轮数"
    )
    summary_max_chars: int = Field(
        default=8000,
        ge=500,
        le=100000,
        description="摘要正文长度上限（字符），超限放弃本次压缩",
    )
    summary_max_tokens: int = Field(
        default=2000, ge=128, le=32000, description="摘要生成的 token 预算"
    )
    summary_input_max_chars: int = Field(
        default=160000, ge=1000, description="摘要输入的长度上限（字符）"
    )
    proactive_prune_tokens: int = Field(
        default=0,
        ge=0,
        description="主动瘦身触发（token），0 表示关闭",
    )
    abort_on_summary_failure: bool = Field(
        default=False,
        description="摘要终态失败时是否中止压缩（False 则降级为确定性摘要）",
    )


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
    # 安全默认值必须为 True：False 等于允许 AI 生成的命令以 CountBot 进程
    # 用户身份读写宿主机任意路径（见安全修复 2026-10-23，CWE-78）。
    # 明确需要全盘访问的部署方可在配置文件中显式设为 false。
    restrict_to_workspace: bool = Field(default=True, description="是否限制命令在工作空间内执行")


class AgentConfig(BaseModel):
    """Agent 行为配置"""
    tool_timeout_seconds: int = Field(
        default=60,
        ge=5,
        le=1800,
        description="主循环工具调用超时（秒）：超时后返回模板错误并提示模型拆分任务",
    )


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
    group_enabled: bool = Field(
        default=True, description="是否允许在群聊中响应消息"
    )
    group_require_mention: bool = Field(
        default=True, description="群聊中是否必须 @机器人 才触发处理"
    )
    group_topic_enabled: bool = Field(
        default=True, description="是否按飞书话题（thread）拆分独立会话"
    )


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


class ServerChanAccountConfig(ChannelAccountConfig):
    """Server酱推送配置（只出不进的消息推送渠道）"""

    sendkey: str = Field(default="", description="Server酱 SendKey（SCT 以 SCT 开头，SC3 以 sctp 开头）")


class ServerChanConfig(ServerChanAccountConfig):
    """Server酱渠道配置"""

    accounts: Dict[str, ServerChanAccountConfig] = Field(default_factory=dict)


class XiaozhiAccountConfig(ChannelAccountConfig):
    """小智AI 机器人配置（MCP Client 模式）"""

    endpoint: str = Field(default="", description="小智AI MCP WebSocket 接入点，如 ws://192.168.1.x:8765")
    enable_conversation: bool = Field(default=False, description="启用对话模式（通过 send_message 工具接收用户消息）")


class XiaozhiConfig(XiaozhiAccountConfig):
    """小智AI渠道配置（MCP Client 模式）"""

    accounts: Dict[str, XiaozhiAccountConfig] = Field(default_factory=dict)


class McpServerConfig(BaseModel):
    """单个 MCP Server 连接配置"""
    id: str = ""
    name: str = ""
    enabled: bool = True
    transport: Optional[Literal["stdio", "streamable_http", "sse"]] = None
    description: str = ""
    include_tools: List[str] = Field(default_factory=lambda: ["*"])
    exclude_tools: List[str] = Field(default_factory=list)
    enable_resources: bool = False
    enable_prompts: bool = False
    command: str = ""
    args: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    url: str = ""
    headers: Dict[str, str] = Field(default_factory=dict)
    timeout: int = Field(default=30, ge=5, le=300)
    connect_timeout: int = Field(default=10, ge=5, le=60)


class McpRegistryConfig(BaseModel):
    """MCP Server 注册表"""
    version: int = 1
    servers: List[McpServerConfig] = Field(default_factory=list)


class McpConfig(BaseModel):
    """MCP 总配置"""
    enabled: bool = Field(default=False, description="是否启用 MCP 功能，默认关闭")
    registry: McpRegistryConfig = Field(default_factory=McpRegistryConfig)


class InjectionConfig(BaseModel):
    """上下文注入开关：逐项控制进入 LLM 请求的内容，默认全部开启（= 历史行为）。"""

    # system prompt 区块
    core_rules: bool = Field(
        default=True,
        description="核心规则段（CountBot 规则/工具执行/文件技能/记忆/知识库/安全），关闭后仅保留最小身份",
    )
    external_coding_guidance: bool = Field(
        default=True, description="外部编码代理指引（external_coding_agent 使用说明）"
    )
    skills_always: bool = Field(default=True, description="always=true 技能全文注入")
    skills_summary: bool = Field(default=True, description="已启用技能摘要（name+description）注入")
    agent_teams: bool = Field(default=True, description="已激活多智能体团队区块注入")

    # user 消息动态注入
    dynamic_context: bool = Field(
        default=True, description="当前时间/用户资料/会话摘要/渠道信息注入首条 user 消息"
    )
    memory: bool = Field(
        default=True, description="长期记忆注入（断言层中最重要的一批条目）"
    )
    team_reminder: bool = Field(default=True, description="检测到 @团队名 时注入 workflow_run 提醒")

    # 工具
    disabled_tools: List[str] = Field(
        default_factory=list, description="禁用的工具名列表，不出现在工具定义里且不可调用"
    )

    # 后台维护：不注入请求，消耗 token 配额
    auto_memory_summary: bool = Field(
        default=True, description="后台自动记忆维护（溢出历史/整会话沉淀到 MEMORY.md）"
    )


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
    serverchan: ServerChanConfig = Field(default_factory=ServerChanConfig)


class AppConfig(BaseModel):
    """应用配置"""
    providers: Dict[str, ProviderConfig] = Field(default_factory=dict)
    model: ModelConfig = Field(default_factory=ModelConfig)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    compaction: CompactionConfig = Field(default_factory=CompactionConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    persona: PersonaConfig = Field(default_factory=PersonaConfig)
    mcp: McpConfig = Field(default_factory=McpConfig)
    injection: InjectionConfig = Field(default_factory=InjectionConfig)
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

        self._migrate_provider_models()

    def _migrate_provider_models(self) -> None:
        """把改造前的单模型配置迁移成供应商模型清单。

        存量配置里没有 api_type / models 两个字段，这里在加载时就地补齐，
        避免每个读 provider 的地方各自兜底：
        - api_type 为空时按 provider_id 推断（与 factory.resolve_api_type 一致）
        - provider.model 有值但清单为空时补一条 manual 条目
        - 全局选中模型所属供应商的清单里没有它时也补一条，保证下拉能显示当前项
        """
        from backend.modules.providers.factory import resolve_api_type

        for provider_id, provider_config in self.providers.items():
            # 读盘时 api_type 已被 Literal 默认值填成 chat-completions，
            # 因此需要靠 explicit 标记区分「用户选的」和「schema 默认的」：
            # 只有非默认值才视为用户显式选择，否则按 provider_id 推断。
            provider_config.api_type = resolve_api_type(
                provider_id,
                provider_config.api_type,
                explicit=provider_config.api_type != "openai-chat-completions",
            )

            legacy_model = (provider_config.model or "").strip()
            if legacy_model and provider_config.find_model(legacy_model) is None:
                provider_config.ensure_model(legacy_model, source="manual")

        selected_provider_id = (self.model.provider or "").strip()
        selected_model = (self.model.model or "").strip()
        selected_provider = self.providers.get(selected_provider_id)
        if selected_provider is not None and selected_model:
            if selected_provider.find_model(selected_model) is None:
                selected_provider.ensure_model(selected_model, source="manual")
