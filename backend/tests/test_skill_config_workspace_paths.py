"""技能配置接口应始终跟随当前 workspace/skills 目录。"""

import asyncio
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.api.skills import (  # noqa: E402
    get_skill_config,
    get_skill_config_help,
    get_skill_config_schema,
    get_skill_config_status,
    get_workspace_skills_dir,
)
from backend.modules.config.loader import config_loader  # noqa: E402


EMAIL_CONFIG_TEMPLATE = {
    "default_mailbox": "qq",
    "qq_email": {
        "email": "demo@qq.com",
        "auth_code": "auth-code",
        "imap_server": "imap.qq.com",
        "imap_port": 993,
        "smtp_server": "smtp.qq.com",
        "smtp_port": 465,
    },
    "163_email": {
        "email": "demo@163.com",
        "auth_password": "auth-password",
        "pop_server": "pop.163.com",
        "pop_port": 995,
        "smtp_server": "smtp.163.com",
        "smtp_port": 465,
        "note": "163 uses POP3",
    },
    "last_check_time": "",
}


def write_email_skill(workspace: Path, mailbox: str, help_content: str) -> None:
    """在指定 workspace 下创建最小 email 配置文件。"""
    skill_dir = workspace / "skills" / "email"
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    config = dict(EMAIL_CONFIG_TEMPLATE)
    config["qq_email"] = dict(EMAIL_CONFIG_TEMPLATE["qq_email"])
    config["163_email"] = dict(EMAIL_CONFIG_TEMPLATE["163_email"])
    config["qq_email"]["email"] = mailbox

    (scripts_dir / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (skill_dir / "config.help.md").write_text(help_content, encoding="utf-8")


def test_skill_config_endpoints_follow_workspace_switch() -> None:
    """切换 workspace.path 后，配置接口应读取新的 workspace/skills。"""
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        workspace_one = root / "workspace-one"
        workspace_two = root / "workspace-two"

        write_email_skill(workspace_one, "one@qq.com", "help from workspace one")
        write_email_skill(workspace_two, "two@qq.com", "help from workspace two")

        original_workspace_path = config_loader.config.workspace.path

        try:
            config_loader.config.workspace.path = str(workspace_one)
            assert get_workspace_skills_dir() == (workspace_one / "skills").resolve()

            config_one = asyncio.run(get_skill_config("email"))
            status_one = asyncio.run(get_skill_config_status("email"))
            help_one = asyncio.run(get_skill_config_help("email"))
            schema_one = asyncio.run(get_skill_config_schema("email"))

            assert config_one.has_config is True
            assert config_one.config["qq_email"]["email"] == "one@qq.com"
            assert status_one.status == "valid"
            assert help_one.has_help is True
            assert help_one.content == "help from workspace one"
            assert schema_one.has_schema is True
            assert schema_one.schema_definition is not None
            assert schema_one.schema_definition["skill_name"] == "email"
            assert schema_one.model_dump(by_alias=True)["schema"]["skill_name"] == "email"

            config_loader.config.workspace.path = str(workspace_two)
            assert get_workspace_skills_dir() == (workspace_two / "skills").resolve()

            config_two = asyncio.run(get_skill_config("email"))
            help_two = asyncio.run(get_skill_config_help("email"))

            assert config_two.has_config is True
            assert config_two.config["qq_email"]["email"] == "two@qq.com"
            assert help_two.has_help is True
            assert help_two.content == "help from workspace two"
        finally:
            config_loader.config.workspace.path = original_workspace_path


def test_baidu_search_schema_response_contains_schema_payload() -> None:
    """baidu-search 的 schema 响应应包含前端需要的 schema 字段。"""
    schema_response = asyncio.run(get_skill_config_schema("baidu-search"))

    assert schema_response.has_schema is True
    assert schema_response.schema_definition is not None
    assert schema_response.schema_definition["skill_name"] == "baidu-search"
    assert schema_response.model_dump(by_alias=True)["schema"]["skill_name"] == "baidu-search"


def main() -> int:
    try:
        test_skill_config_endpoints_follow_workspace_switch()
        test_baidu_search_schema_response_contains_schema_payload()
        print("✅ skill config workspace path test passed")
        return 0
    except Exception as exc:
        print(f"❌ skill config workspace path test failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())