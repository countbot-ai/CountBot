"""导入配置后立即应用到运行态的回归测试。"""

import asyncio
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.api.settings import ImportSettingsRequest, import_settings  # noqa: E402
from backend.modules.config.loader import config_loader  # noqa: E402


class RecordingMessageHandler:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def reload_config(self, **kwargs) -> None:
        self.calls.append(kwargs)


class RecordingContextBuilder:
    def __init__(self) -> None:
        self.persona_updates = []
        self.workspace_updates = []

    def update_persona_config(self, persona) -> None:
        self.persona_updates.append(persona)

    def update_workspace(self, workspace: Path) -> None:
        self.workspace_updates.append(workspace)


class FakeLiteLLMProvider:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


async def test_import_applies_runtime_reload_immediately() -> None:
    original_config = config_loader.config.model_copy(deep=True)

    async def fake_save_config(new_config) -> None:
        config_loader.config = new_config.model_copy(deep=True)

    try:
        with TemporaryDirectory() as temp_dir:
            workspace_path = Path(temp_dir) / "imported-workspace"
            workspace_path.mkdir(parents=True, exist_ok=True)
            (workspace_path / "temp").mkdir(exist_ok=True)

            handler = RecordingMessageHandler()
            context_builder = RecordingContextBuilder()
            scheduler = SimpleNamespace(trigger_reschedule=AsyncMock())
            req = SimpleNamespace(
                app=SimpleNamespace(
                    state=SimpleNamespace(
                        message_handler=handler,
                        shared={"context_builder": context_builder},
                        cron_scheduler=scheduler,
                    )
                )
            )

            import_request = ImportSettingsRequest(
                version="1.0.0",
                merge=False,
                config={
                    "providers": {
                        "zhipu": {
                            "enabled": True,
                            "api_key": "imported-key",
                            "api_base": "https://example.test/v1",
                        }
                    },
                    "model": {
                        "provider": "zhipu",
                        "model": "imported-model",
                        "temperature": 0.33,
                        "max_tokens": 2048,
                        "max_iterations": 7,
                    },
                    "workspace": {"path": str(workspace_path)},
                    "persona": {
                        "ai_name": "导入助手",
                        "user_name": "测试用户",
                        "user_address": "杭州",
                        "output_language": "英文",
                        "personality": "grumpy",
                        "custom_personality": "",
                        "max_history_messages": 88,
                        "heartbeat": {
                            "enabled": True,
                            "channel": "feishu",
                            "chat_id": "chat-1",
                            "schedule": "0 * * * *",
                            "idle_threshold_hours": 4,
                            "quiet_start": 21,
                            "quiet_end": 8,
                            "max_greets_per_day": 2,
                        },
                    },
                },
            )

            with patch.object(config_loader, "save_config", AsyncMock(side_effect=fake_save_config)):
                with patch("backend.modules.providers.litellm_provider.LiteLLMProvider", FakeLiteLLMProvider):
                    with patch(
                        "backend.modules.providers.registry.get_provider_metadata",
                        return_value=SimpleNamespace(default_api_base="https://metadata.example/v1"),
                    ):
                        with patch("backend.database.get_db_session_factory", return_value=object()):
                            with patch(
                                "backend.modules.agent.heartbeat.ensure_heartbeat_job",
                                AsyncMock(),
                            ) as ensure_heartbeat_job:
                                response = await import_settings(import_request, req)

            workspace_call = next((call for call in handler.calls if "workspace" in call), None)
            model_call = next((call for call in handler.calls if "model" in call), None)

            assert response["success"] is True
            assert response["settings"].model.model == "imported-model"
            assert workspace_call is not None
            assert workspace_call["workspace"] == workspace_path.resolve()
            assert model_call is not None
            assert model_call["model"] == "imported-model"
            assert model_call["persona_config"].output_language == "英文"
            assert isinstance(model_call["provider"], FakeLiteLLMProvider)
            assert context_builder.persona_updates[-1].ai_name == "导入助手"
            assert context_builder.workspace_updates[-1] == workspace_path.resolve()
            assert req.app.state.shared["workspace"] == workspace_path.resolve()
            ensure_heartbeat_job.assert_awaited_once()
            scheduler.trigger_reschedule.assert_awaited_once()

    finally:
        config_loader.config = original_config


def main() -> int:
    try:
        asyncio.run(test_import_applies_runtime_reload_immediately())
        print("✅ import settings 会立即热重载运行时配置")
        return 0
    except Exception as exc:
        print(f"❌ import settings 热重载验证失败: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())