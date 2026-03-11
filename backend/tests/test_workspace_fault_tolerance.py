"""workspace 路径容错回归测试。"""

import asyncio
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.api.settings import set_workspace_path  # noqa: E402
from backend.modules.config.loader import ConfigLoader, config_loader  # noqa: E402


class FakeResult:
    def __init__(self, settings):
        self._settings = settings

    def scalars(self):
        return self

    def all(self):
        return self._settings


class FakeSession:
    def __init__(self, settings):
        self._settings = settings

    async def execute(self, _query):
        return FakeResult(self._settings)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeRequest:
    def __init__(self, body):
        self._body = body
        self.app = SimpleNamespace(
            state=SimpleNamespace(message_handler=None, shared=None)
        )

    async def json(self):
        return self._body


def test_loader_falls_back_to_default_workspace_on_invalid_path() -> None:
    with TemporaryDirectory() as temp_dir:
        fallback_path = Path(temp_dir) / "fallback-workspace"
        fallback_path.mkdir(parents=True, exist_ok=True)
        (fallback_path / "temp").mkdir(parents=True, exist_ok=True)

        loader = ConfigLoader()
        settings = [
            SimpleNamespace(
                key="config.workspace.path",
                value=json.dumps("bad-workspace-path"),
            )
        ]

        with patch("backend.modules.config.loader.AsyncSessionLocal", return_value=FakeSession(settings)):
            with patch(
                "backend.modules.workspace.workspace_manager.prepare_workspace_path",
                side_effect=OSError("boom"),
            ):
                with patch(
                    "backend.modules.workspace.workspace_manager._get_default_workspace_path",
                    return_value=fallback_path,
                ):
                    config = asyncio.run(loader.load())

        assert config.workspace.path == str(fallback_path)
        assert loader.config.workspace.path == str(fallback_path)


def test_save_endpoint_rejects_invalid_workspace_without_persisting() -> None:
    original_config = config_loader.config.model_copy(deep=True)
    config_loader.config.workspace.path = "keep-current-workspace"

    try:
        with patch(
            "backend.modules.workspace.workspace_manager.prepare_workspace_path",
            side_effect=OSError("invalid path"),
        ):
            with patch.object(config_loader, "save_config", AsyncMock()) as save_config_mock:
                try:
                    asyncio.run(set_workspace_path(FakeRequest({"path": "bad-path"})))
                    raise AssertionError("expected HTTPException")
                except HTTPException as exc:
                    assert exc.status_code == 400
                    assert "工作空间路径不可用" in exc.detail

                save_config_mock.assert_not_awaited()
                assert config_loader.config.workspace.path == "keep-current-workspace"
    finally:
        config_loader.config = original_config


def test_save_config_validates_workspace_before_mutating_loader() -> None:
    loader = ConfigLoader()
    loader.config.workspace.path = "original-workspace"
    candidate = loader.config.model_copy(deep=True)
    candidate.workspace.path = "bad-workspace"

    with patch(
        "backend.modules.workspace.workspace_manager.prepare_workspace_path",
        side_effect=OSError("bad workspace"),
    ):
        try:
            asyncio.run(loader.save_config(candidate))
            raise AssertionError("expected workspace validation failure")
        except OSError as exc:
            assert "bad workspace" in str(exc)

    assert loader.config.workspace.path == "original-workspace"


def main() -> int:
    tests = [
        ("loader fallback", test_loader_falls_back_to_default_workspace_on_invalid_path),
        ("save endpoint reject invalid path", test_save_endpoint_rejects_invalid_workspace_without_persisting),
        ("save_config validate before mutate", test_save_config_validates_workspace_before_mutating_loader),
    ]

    failed = []
    for name, test_func in tests:
        try:
            test_func()
            print(f"✅ {name}")
        except Exception as exc:
            failed.append((name, exc))
            print(f"❌ {name}: {exc}")

    if failed:
        return 1

    print("\nworkspace fault tolerance tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())