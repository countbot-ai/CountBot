"""技能配置Schema数据定义 - 固定Schema数据"""

from typing import List


def _build_ima_fields(include_default_knowledge_base: bool) -> List[dict]:
    fields = [
        {
            "key": "client_id",
            "type": "string",
            "label": "Client ID",
            "description": "IMA OpenAPI Client ID",
            "required": True,
            "placeholder": "请输入 IMA Client ID",
            "help_url": "https://ima.qq.com/agent-interface"
        },
        {
            "key": "api_key",
            "type": "password",
            "label": "API Key",
            "description": "IMA OpenAPI API Key",
            "required": True,
            "sensitive": True,
            "placeholder": "请输入 IMA API Key",
            "help_url": "https://ima.qq.com/agent-interface"
        },
        {
            "key": "base_url",
            "type": "string",
            "label": "Base URL",
            "description": "IMA OpenAPI 服务地址，默认无需修改",
            "default": "https://ima.qq.com",
            "placeholder": "https://ima.qq.com"
        },
        {
            "key": "request_timeout_seconds",
            "type": "number",
            "label": "请求超时秒数",
            "description": "调用 IMA API 时的 HTTP 超时时间",
            "default": 30,
            "min": 5,
            "max": 300
        }
    ]

    if include_default_knowledge_base:
        fields.extend([
            {
                "key": "default_knowledge_base",
                "type": "object",
                "label": "默认知识库",
                "description": "可选。把默认知识库 ID、名称、文件夹 ID 作为一个前端配置块统一管理",
                "collapsible": True,
                "fields": [
                    {
                        "key": "id",
                        "type": "string",
                        "label": "默认知识库 ID",
                        "description": "可选。配置后可作为 list/search/upload/import 的默认知识库",
                        "default": "",
                        "placeholder": "例如 O2489Cx5eMgYRl0BwFeMlpIvcqbzdwn0cNwN8wZH094="
                    },
                    {
                        "key": "name",
                        "type": "string",
                        "label": "默认知识库名称",
                        "description": "可选。若未填写默认知识库 ID，可通过名称自动解析知识库",
                        "default": "",
                        "placeholder": "例如 个人知识库"
                    },
                    {
                        "key": "folder_id",
                        "type": "string",
                        "label": "默认知识库文件夹 ID",
                        "description": "可选。上传文件或导入网页时默认写入该文件夹；为空则写入根目录",
                        "default": "",
                        "placeholder": "例如 0019f4010ac04db1"
                    }
                ]
            },
            {
                "key": "restrict_search_to_default_knowledge_base",
                "type": "boolean",
                "label": "默认只搜索指定知识库",
                "description": "开启后，search-kb 在未显式指定知识库时只搜索默认知识库",
                "default": False
            }
        ])

    return fields


# 固定Schema定义 - 为每个需要配置的技能预定义字段
SKILL_SCHEMAS = {
    "baidu-search": {
        "skill_name": "baidu-search",
        "version": "1.0.0",
        "description": "百度搜索API配置",
        "config_file": "scripts/config.json",
        "help_text": "配置百度搜索API以启用搜索功能。\n\n获取API Key：\n1. 访问百度开放平台\n2. 注册并创建应用\n3. 获取API Key\n\n配置说明：\n- API Key：必填，用于调用百度搜索API\n- 最大结果数：建议设置为10-50之间\n- 安全搜索：启用后会过滤不适宜内容",
        "fields": [
            {
                "key": "api_key",
                "type": "password",
                "label": "API Key",
                "description": "百度搜索API密钥",
                "required": True,
                "sensitive": True,
                "placeholder": "请输入百度搜索API Key",
                "help_text": "在百度开放平台创建应用后获取"
            },
            {
                "key": "default_max_results",
                "type": "number",
                "label": "默认最大结果数",
                "description": "搜索返回的默认最大结果数量",
                "default": 10,
                "min": 1,
                "max": 100,
                "help_text": "建议设置为10-50之间，过大可能影响性能"
            },
            {
                "key": "safe_search",
                "type": "boolean",
                "label": "安全搜索",
                "description": "是否启用安全搜索过滤",
                "default": False,
                "help_text": "启用后会过滤不适宜内容"
            }
        ]
    },
    "email": {
        "skill_name": "email",
        "version": "1.1.0",
        "description": "邮件服务配置",
        "config_file": "scripts/config.json",
        "help_file": "config.help.md",
        "fields": [
            {
                "key": "default_mailbox",
                "type": "select",
                "label": "默认邮箱",
                "description": "默认使用的邮箱服务",
                "default": "qq",
                "options": [
                    {"value": "qq", "label": "QQ邮箱"},
                    {"value": "163", "label": "163邮箱"},
                    {"value": "gmail", "label": "Gmail"},
                    {"value": "outlook", "label": "Outlook"},
                    {"value": "custom", "label": "自定义邮箱"}
                ]
            },
            {
                "key": "allowed_read_dirs",
                "type": "string",
                "label": "允许读取的目录",
                "description": "发送附件时允许读取的本地目录，多个目录请用逗号分隔",
                "default": "",
                "placeholder": "D:/Downloads,D:/Documents"
            },
            {
                "key": "allowed_write_dirs",
                "type": "string",
                "label": "允许写入的目录",
                "description": "下载附件时允许写入的本地目录，多个目录请用逗号分隔",
                "default": "",
                "placeholder": "D:/Downloads"
            },
            {
                "key": "qq_email",
                "type": "object",
                "label": "QQ邮箱配置",
                "description": "QQ邮箱服务器配置",
                "collapsible": True,
                "fields": [
                    {
                        "key": "email",
                        "type": "email",
                        "label": "邮箱地址",
                        "description": "QQ邮箱地址",
                        "required": True,
                        "placeholder": "example@qq.com"
                    },
                    {
                        "key": "auth_code",
                        "type": "password",
                        "label": "授权码",
                        "description": "QQ邮箱授权码",
                        "required": True,
                        "sensitive": True,
                        "placeholder": "请输入授权码"
                    },
                    {
                        "key": "receive_protocol",
                        "type": "select",
                        "label": "收件协议",
                        "description": "推荐使用 IMAP",
                        "default": "imap",
                        "options": [
                            {"value": "imap", "label": "IMAP"}
                        ]
                    },
                    {
                        "key": "imap_server",
                        "type": "string",
                        "label": "IMAP服务器",
                        "description": "IMAP服务器地址",
                        "default": "imap.qq.com"
                    },
                    {
                        "key": "imap_port",
                        "type": "number",
                        "label": "IMAP端口",
                        "description": "IMAP服务器端口",
                        "default": 993,
                        "min": 1,
                        "max": 65535
                    },
                    {
                        "key": "imap_tls",
                        "type": "boolean",
                        "label": "IMAP TLS",
                        "description": "是否启用 IMAP TLS/SSL",
                        "default": True
                    },
                    {
                        "key": "smtp_server",
                        "type": "string",
                        "label": "SMTP服务器",
                        "description": "SMTP服务器地址",
                        "default": "smtp.qq.com"
                    },
                    {
                        "key": "smtp_port",
                        "type": "number",
                        "label": "SMTP端口",
                        "description": "SMTP服务器端口",
                        "default": 465,
                        "min": 1,
                        "max": 65535
                    },
                    {
                        "key": "smtp_ssl",
                        "type": "boolean",
                        "label": "SMTP SSL",
                        "description": "是否使用 SMTP SSL，QQ 邮箱默认开启",
                        "default": True
                    },
                    {
                        "key": "mailbox_folder",
                        "type": "string",
                        "label": "默认收件文件夹",
                        "description": "默认收件文件夹名称",
                        "default": "INBOX"
                    },
                    {
                        "key": "reject_unauthorized",
                        "type": "boolean",
                        "label": "校验证书",
                        "description": "是否严格校验服务端证书",
                        "default": True
                    }
                ]
            },
            {
                "key": "163_email",
                "type": "object",
                "label": "163邮箱配置",
                "description": "163邮箱服务器配置",
                "collapsible": True,
                "fields": [
                    {
                        "key": "email",
                        "type": "email",
                        "label": "邮箱地址",
                        "description": "163邮箱地址",
                        "required": True,
                        "placeholder": "example@163.com"
                    },
                    {
                        "key": "auth_password",
                        "type": "password",
                        "label": "授权密码",
                        "description": "163邮箱授权密码",
                        "required": True,
                        "sensitive": True,
                        "placeholder": "请输入授权密码"
                    },
                    {
                        "key": "receive_protocol",
                        "type": "select",
                        "label": "收件协议",
                        "description": "推荐使用 IMAP；如需兼容旧配置也可选择 POP3",
                        "default": "imap",
                        "options": [
                            {"value": "imap", "label": "IMAP"},
                            {"value": "pop3", "label": "POP3"}
                        ]
                    },
                    {
                        "key": "imap_server",
                        "type": "string",
                        "label": "IMAP服务器",
                        "description": "IMAP服务器地址",
                        "default": "imap.163.com"
                    },
                    {
                        "key": "imap_port",
                        "type": "number",
                        "label": "IMAP端口",
                        "description": "IMAP服务器端口",
                        "default": 993,
                        "min": 1,
                        "max": 65535
                    },
                    {
                        "key": "imap_tls",
                        "type": "boolean",
                        "label": "IMAP TLS",
                        "description": "是否启用 IMAP TLS/SSL",
                        "default": True
                    },
                    {
                        "key": "pop_server",
                        "type": "string",
                        "label": "POP服务器",
                        "description": "仅在 POP3 模式下使用",
                        "default": "pop.163.com"
                    },
                    {
                        "key": "pop_port",
                        "type": "number",
                        "label": "POP端口",
                        "description": "仅在 POP3 模式下使用",
                        "default": 995,
                        "min": 1,
                        "max": 65535
                    },
                    {
                        "key": "smtp_server",
                        "type": "string",
                        "label": "SMTP服务器",
                        "description": "SMTP服务器地址",
                        "default": "smtp.163.com"
                    },
                    {
                        "key": "smtp_port",
                        "type": "number",
                        "label": "SMTP端口",
                        "description": "SMTP服务器端口",
                        "default": 465,
                        "min": 1,
                        "max": 65535
                    },
                    {
                        "key": "smtp_ssl",
                        "type": "boolean",
                        "label": "SMTP SSL",
                        "description": "是否使用 SMTP SSL",
                        "default": True
                    },
                    {
                        "key": "mailbox_folder",
                        "type": "string",
                        "label": "默认收件文件夹",
                        "description": "默认收件文件夹名称",
                        "default": "INBOX"
                    },
                    {
                        "key": "reject_unauthorized",
                        "type": "boolean",
                        "label": "校验证书",
                        "description": "是否严格校验服务端证书",
                        "default": True
                    }
                ]
            },
            {
                "key": "gmail_email",
                "type": "object",
                "label": "Gmail 配置",
                "description": "Gmail IMAP/SMTP 配置",
                "collapsible": True,
                "fields": [
                    {
                        "key": "email",
                        "type": "email",
                        "label": "邮箱地址",
                        "description": "Gmail 地址",
                        "required": True,
                        "placeholder": "example@gmail.com"
                    },
                    {
                        "key": "password",
                        "type": "password",
                        "label": "应用专用密码",
                        "description": "建议使用 App Password",
                        "required": True,
                        "sensitive": True,
                        "placeholder": "请输入应用专用密码"
                    },
                    {
                        "key": "receive_protocol",
                        "type": "select",
                        "label": "收件协议",
                        "description": "Gmail 推荐使用 IMAP",
                        "default": "imap",
                        "options": [
                            {"value": "imap", "label": "IMAP"}
                        ]
                    },
                    {
                        "key": "imap_server",
                        "type": "string",
                        "label": "IMAP服务器",
                        "description": "IMAP服务器地址",
                        "default": "imap.gmail.com"
                    },
                    {
                        "key": "imap_port",
                        "type": "number",
                        "label": "IMAP端口",
                        "description": "IMAP服务器端口",
                        "default": 993,
                        "min": 1,
                        "max": 65535
                    },
                    {
                        "key": "imap_tls",
                        "type": "boolean",
                        "label": "IMAP TLS",
                        "description": "是否启用 IMAP TLS/SSL",
                        "default": True
                    },
                    {
                        "key": "smtp_server",
                        "type": "string",
                        "label": "SMTP服务器",
                        "description": "SMTP服务器地址",
                        "default": "smtp.gmail.com"
                    },
                    {
                        "key": "smtp_port",
                        "type": "number",
                        "label": "SMTP端口",
                        "description": "SMTP服务器端口",
                        "default": 587,
                        "min": 1,
                        "max": 65535
                    },
                    {
                        "key": "smtp_ssl",
                        "type": "boolean",
                        "label": "SMTP SSL",
                        "description": "587 端口通常关闭直连 SSL，由程序自动尝试 STARTTLS",
                        "default": False
                    },
                    {
                        "key": "mailbox_folder",
                        "type": "string",
                        "label": "默认收件文件夹",
                        "description": "默认收件文件夹名称",
                        "default": "INBOX"
                    },
                    {
                        "key": "reject_unauthorized",
                        "type": "boolean",
                        "label": "校验证书",
                        "description": "是否严格校验服务端证书",
                        "default": True
                    }
                ]
            },
            {
                "key": "outlook_email",
                "type": "object",
                "label": "Outlook 配置",
                "description": "Outlook IMAP/SMTP 配置",
                "collapsible": True,
                "fields": [
                    {
                        "key": "email",
                        "type": "email",
                        "label": "邮箱地址",
                        "description": "Outlook 邮箱地址",
                        "required": True,
                        "placeholder": "example@outlook.com"
                    },
                    {
                        "key": "password",
                        "type": "password",
                        "label": "密码或应用专用密码",
                        "description": "Outlook 登录密码或应用专用密码",
                        "required": True,
                        "sensitive": True,
                        "placeholder": "请输入密码"
                    },
                    {
                        "key": "receive_protocol",
                        "type": "select",
                        "label": "收件协议",
                        "description": "Outlook 推荐使用 IMAP",
                        "default": "imap",
                        "options": [
                            {"value": "imap", "label": "IMAP"}
                        ]
                    },
                    {
                        "key": "imap_server",
                        "type": "string",
                        "label": "IMAP服务器",
                        "description": "IMAP服务器地址",
                        "default": "outlook.office365.com"
                    },
                    {
                        "key": "imap_port",
                        "type": "number",
                        "label": "IMAP端口",
                        "description": "IMAP服务器端口",
                        "default": 993,
                        "min": 1,
                        "max": 65535
                    },
                    {
                        "key": "imap_tls",
                        "type": "boolean",
                        "label": "IMAP TLS",
                        "description": "是否启用 IMAP TLS/SSL",
                        "default": True
                    },
                    {
                        "key": "smtp_server",
                        "type": "string",
                        "label": "SMTP服务器",
                        "description": "SMTP服务器地址",
                        "default": "smtp.office365.com"
                    },
                    {
                        "key": "smtp_port",
                        "type": "number",
                        "label": "SMTP端口",
                        "description": "SMTP服务器端口",
                        "default": 587,
                        "min": 1,
                        "max": 65535
                    },
                    {
                        "key": "smtp_ssl",
                        "type": "boolean",
                        "label": "SMTP SSL",
                        "description": "587 端口通常关闭直连 SSL，由程序自动尝试 STARTTLS",
                        "default": False
                    },
                    {
                        "key": "mailbox_folder",
                        "type": "string",
                        "label": "默认收件文件夹",
                        "description": "默认收件文件夹名称",
                        "default": "INBOX"
                    },
                    {
                        "key": "reject_unauthorized",
                        "type": "boolean",
                        "label": "校验证书",
                        "description": "是否严格校验服务端证书",
                        "default": True
                    }
                ]
            },
            {
                "key": "custom_email",
                "type": "object",
                "label": "自定义邮箱配置",
                "description": "通用 IMAP/SMTP 或 POP3/SMTP 配置",
                "collapsible": True,
                "fields": [
                    {
                        "key": "email",
                        "type": "email",
                        "label": "邮箱地址",
                        "description": "自定义邮箱地址",
                        "required": True,
                        "placeholder": "example@company.com"
                    },
                    {
                        "key": "password",
                        "type": "password",
                        "label": "密码或授权码",
                        "description": "邮箱登录密码或授权码",
                        "required": True,
                        "sensitive": True,
                        "placeholder": "请输入密码或授权码"
                    },
                    {
                        "key": "receive_protocol",
                        "type": "select",
                        "label": "收件协议",
                        "description": "推荐使用 IMAP，只有旧系统才考虑 POP3",
                        "default": "imap",
                        "options": [
                            {"value": "imap", "label": "IMAP"},
                            {"value": "pop3", "label": "POP3"}
                        ]
                    },
                    {
                        "key": "imap_server",
                        "type": "string",
                        "label": "IMAP服务器",
                        "description": "IMAP服务器地址",
                        "default": "imap.example.com"
                    },
                    {
                        "key": "imap_port",
                        "type": "number",
                        "label": "IMAP端口",
                        "description": "IMAP服务器端口",
                        "default": 993,
                        "min": 1,
                        "max": 65535
                    },
                    {
                        "key": "imap_tls",
                        "type": "boolean",
                        "label": "IMAP TLS",
                        "description": "是否启用 IMAP TLS/SSL",
                        "default": True
                    },
                    {
                        "key": "pop_server",
                        "type": "string",
                        "label": "POP服务器",
                        "description": "仅在 POP3 模式下使用",
                        "default": "pop.example.com"
                    },
                    {
                        "key": "pop_port",
                        "type": "number",
                        "label": "POP端口",
                        "description": "仅在 POP3 模式下使用",
                        "default": 995,
                        "min": 1,
                        "max": 65535
                    },
                    {
                        "key": "smtp_server",
                        "type": "string",
                        "label": "SMTP服务器",
                        "description": "SMTP服务器地址",
                        "default": "smtp.example.com"
                    },
                    {
                        "key": "smtp_port",
                        "type": "number",
                        "label": "SMTP端口",
                        "description": "SMTP服务器端口",
                        "default": 587,
                        "min": 1,
                        "max": 65535
                    },
                    {
                        "key": "smtp_ssl",
                        "type": "boolean",
                        "label": "SMTP SSL",
                        "description": "是否使用 SMTP SSL",
                        "default": False
                    },
                    {
                        "key": "mailbox_folder",
                        "type": "string",
                        "label": "默认收件文件夹",
                        "description": "默认收件文件夹名称",
                        "default": "INBOX"
                    },
                    {
                        "key": "reject_unauthorized",
                        "type": "boolean",
                        "label": "校验证书",
                        "description": "是否严格校验服务端证书",
                        "default": True
                    }
                ]
            },
            {
                "key": "last_check_time",
                "type": "string",
                "label": "最后检查时间",
                "description": "最后一次检查邮件的时间",
                "readonly": True
            }
        ]
    },
    "image-analysis": {
        "skill_name": "image-analysis",
        "version": "1.0.0",
        "description": "图像分析服务配置",
        "config_file": "scripts/config.json",
        "help_file": "config.help.md",
        "fields": [
            {
                "key": "default_model",
                "type": "select",
                "label": "默认模型",
                "description": "默认使用的图像分析模型",
                "default": "qwen",
                "options": [
                    {"value": "qwen", "label": "通义千问"},
                    {"value": "zhipu", "label": "智谱AI"}
                ]
            },
            {
                "key": "zhipu",
                "type": "object",
                "label": "智谱AI配置",
                "description": "智谱AI图像分析配置",
                "collapsible": True,
                "fields": [
                    {
                        "key": "api_key",
                        "type": "password",
                        "label": "API Key",
                        "description": "智谱AI API密钥",
                        "required": True,
                        "sensitive": True,
                        "placeholder": "请输入API Key"
                    },
                    {
                        "key": "model",
                        "type": "string",
                        "label": "模型名称",
                        "description": "使用的模型名称",
                        "default": "glm-4.6v-flash"
                    },
                    {
                        "key": "base_url",
                        "type": "string",
                        "label": "API端点",
                        "description": "API端点URL",
                        "default": "https://open.bigmodel.cn/api/paas/v4/chat/completions"
                    }
                ]
            },
            {
                "key": "qwen",
                "type": "object",
                "label": "通义千问配置",
                "description": "通义千问图像分析配置",
                "collapsible": True,
                "fields": [
                    {
                        "key": "api_key",
                        "type": "password",
                        "label": "API Key",
                        "description": "通义千问API密钥",
                        "required": True,
                        "sensitive": True,
                        "placeholder": "请输入API Key"
                    },
                    {
                        "key": "model",
                        "type": "string",
                        "label": "模型名称",
                        "description": "使用的模型名称",
                        "default": "qwen3-omni-flash-2025-12-01"
                    },
                    {
                        "key": "base_url",
                        "type": "string",
                        "label": "API端点",
                        "description": "API端点URL",
                        "default": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
                    },
                    {
                        "key": "region",
                        "type": "string",
                        "label": "区域",
                        "description": "服务区域",
                        "default": "beijing"
                    }
                ]
            }
        ]
    },
    "image-gen": {
        "skill_name": "image-gen",
        "version": "1.0.0",
        "description": "图像生成服务配置",
        "config_file": "scripts/config.json",
        "help_file": "config.help.md",
        "fields": [
            {
                "key": "api_token",
                "type": "password",
                "label": "API Token",
                "description": "图像生成服务API令牌",
                "required": True,
                "sensitive": True,
                "placeholder": "请输入API Token"
            }
        ]
    },
    "map": {
        "skill_name": "map",
        "version": "1.0.0",
        "description": "地图服务配置",
        "config_file": "scripts/config.json",
        "help_file": "config.help.md",
        "fields": [
            {
                "key": "amap_key",
                "type": "password",
                "label": "高德地图API Key",
                "description": "高德地图API密钥",
                "required": True,
                "sensitive": True,
                "placeholder": "请输入高德地图API Key"
            }
        ]
    },
    "web-design": {
        "skill_name": "web-design",
        "version": "1.0.0",
        "description": "网页设计服务配置",
        "config_file": "scripts/config.json",
        "help_file": "config.help.md",
        "fields": [
            {
                "key": "api_token",
                "type": "password",
                "label": "API Token",
                "description": "网页设计服务API令牌",
                "required": True,
                "sensitive": True,
                "placeholder": "请输入API Token"
            }
        ]
    },
    "ima-knowledge-base": {
        "skill_name": "ima-knowledge-base",
        "version": "1.0.0",
        "description": "IMA OpenAPI 知识库工具配置",
        "config_file": "scripts/config.json",
        "help_file": "config.help.md",
        "fields": _build_ima_fields(include_default_knowledge_base=True)
    },
    "ima-notes": {
        "skill_name": "ima-notes",
        "version": "1.0.0",
        "description": "IMA OpenAPI 笔记工具配置",
        "config_file": "scripts/config.json",
        "help_file": "config.help.md",
        "fields": _build_ima_fields(include_default_knowledge_base=False)
    },
    "ima-skill": {
        "skill_name": "ima-skill",
        "version": "2.1.0",
        "description": "IMA OpenAPI 单入口工具配置",
        "config_file": "scripts/config.json",
        "help_file": "config.help.md",
        "fields": _build_ima_fields(include_default_knowledge_base=True)
    }
}
