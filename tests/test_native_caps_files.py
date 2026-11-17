"""Office / 文档走 DeepSeek Files API 的 purpose 映射与门禁回归测试。"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.native_caps import files as native_files
from backend.modules.config.schema import (
    DEFAULT_MODEL_ID,
    build_default_provider_config,
)


def test_deepseek_default_model_has_native_capabilities():
    """新装默认的 DeepSeek 模型应直接带上全部原生能力。"""
    provider = build_default_provider_config()
    model = provider.find_model(DEFAULT_MODEL_ID)
    assert model is not None
    caps = model.native_capabilities
    assert caps.web_search and caps.read_url and caps.safety_check
    assert caps.asr and caps.tts
    assert caps.document_parsing == "rich"


@pytest.mark.parametrize(
    ("name", "mode", "expected"),
    [
        ("report.pdf", "text", "text_recognition"),
        ("report.pdf", "rich", "rich_layout_recognition"),
        ("contract.docx", "text", "text_recognition"),
        ("contract.docx", "rich", "rich_layout_recognition"),
        ("slides.pptx", "rich", "rich_layout_recognition"),
        ("legacy.doc", "text", "text_recognition"),
        ("sheet.xlsx", "text", "user_data"),
        # 表格无论哪种模式都必须走 user_data：官方只对 PDF/Word/PPT 做版面解析。
        ("sheet.xlsx", "rich", "user_data"),
        ("legacy.xls", "rich", "user_data"),
        ("notes.md", "rich", "user_data"),
        ("main.py", "text", "user_data"),
    ],
)
def test_resolve_purpose(name, mode, expected):
    assert native_files.resolve_purpose(Path(name), mode) == expected


def _write(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_build_document_blocks_uploads_office_with_expected_purpose(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    docx = _write(workspace / "uploads" / "contract.docx", b"docx")
    xlsx = _write(workspace / "uploads" / "sheet.xlsx", b"xlsx")
    calls = []

    async def fake_upload(*, api_base, api_key, path, purpose):
        calls.append((path.name, purpose))
        return f"file-{path.suffix.lstrip('.')}"

    monkeypatch.setattr(native_files, "upload_file", fake_upload)

    blocks, handled = asyncio.run(
        native_files.build_document_blocks(
            ["uploads/contract.docx", "uploads/sheet.xlsx"],
            workspace=workspace,
            api_base="https://api.deepseek.com/",
            api_key="test-placeholder",
            provider_id="deepseek",
            model="deepseek-flash",
            capabilities={"document_parsing": "rich"},
        )
    )

    assert calls == [
        ("contract.docx", "rich_layout_recognition"),
        ("sheet.xlsx", "user_data"),
    ]
    assert handled == {"uploads/contract.docx", "uploads/sheet.xlsx"}
    assert [block["filename"] for block in blocks] == ["contract.docx", "sheet.xlsx"]
    assert all(block["block_type"] == "document" for block in blocks)


def test_build_document_blocks_skips_failed_upload_for_path_fallback(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    _write(workspace / "uploads" / "broken.docx", b"not-a-docx")

    async def failing_upload(**_kwargs):
        return None

    monkeypatch.setattr(native_files, "upload_file", failing_upload)

    blocks, handled = asyncio.run(
        native_files.build_document_blocks(
            ["uploads/broken.docx"],
            workspace=workspace,
            api_base="https://api.deepseek.com/",
            api_key="test-placeholder",
            provider_id="deepseek",
            model="deepseek-flash",
            capabilities={"document_parsing": "rich"},
        )
    )

    # 上传失败不能吞掉附件：不返回块、不标记已处理，调用方继续走本地路径。
    assert blocks == []
    assert handled == set()


@pytest.mark.parametrize(
    ("provider_id", "model", "capabilities"),
    [
        ("deepseek", "deepseek-flash", {"document_parsing": "off"}),
        ("custom_openai", "ds-v4.1-flash", {}),
        ("custom_openai", "ds-v4.1-flash", None),
    ],
)
def test_build_document_blocks_gate_keeps_original_behavior(
    tmp_path, monkeypatch, provider_id, model, capabilities
):
    workspace = tmp_path / "ws"
    _write(workspace / "uploads" / "contract.docx", b"docx")

    async def unexpected_upload(**_kwargs):
        raise AssertionError("未启用能力时不应触发上传")

    monkeypatch.setattr(native_files, "upload_file", unexpected_upload)

    blocks, handled = asyncio.run(
        native_files.build_document_blocks(
            ["uploads/contract.docx"],
            workspace=workspace,
            api_base="https://relay.example.com/v1",
            api_key="test-placeholder",
            provider_id=provider_id,
            model=model,
            capabilities=capabilities,
        )
    )

    assert blocks == []
    assert handled == set()


def test_build_document_blocks_allows_relay_provider(tmp_path, monkeypatch):
    """中转或自定义供应商勾选后按原生能力上传。"""
    workspace = tmp_path / "ws"
    _write(workspace / "uploads" / "contract.docx", b"docx")
    calls = []

    async def fake_upload(*, api_base, api_key, path, purpose):
        calls.append((api_base, path.name, purpose))
        return "file-relay"

    monkeypatch.setattr(native_files, "upload_file", fake_upload)

    blocks, handled = asyncio.run(
        native_files.build_document_blocks(
            ["uploads/contract.docx"],
            workspace=workspace,
            api_base="https://relay.example.com/v1",
            api_key="test-placeholder",
            provider_id="custom_openai",
            model="ds-v4.1-flash",
            capabilities={"document_parsing": "text"},
        )
    )

    assert calls == [("https://relay.example.com/v1", "contract.docx", "text_recognition")]
    assert handled == {"uploads/contract.docx"}
    assert blocks[0]["file_id"] == "file-relay"


def test_build_document_blocks_accepts_any_deepseek_model(tmp_path, monkeypatch):
    """Pro 等 DeepSeek 模型同样可用。"""
    workspace = tmp_path / "ws"
    _write(workspace / "uploads" / "contract.docx", b"docx")

    async def fake_upload(**kwargs):
        return "file-api-pro"

    monkeypatch.setattr(native_files, "upload_file", fake_upload)

    blocks, handled = asyncio.run(
        native_files.build_document_blocks(
            ["uploads/contract.docx"],
            workspace=workspace,
            api_base="https://api.deepseek.com/",
            api_key="test-placeholder",
            provider_id="deepseek",
            model="deepseek-v4-pro",
            capabilities={"document_parsing": "text"},
        )
    )

    assert handled == {"uploads/contract.docx"}
    assert blocks[0]["file_id"] == "file-api-pro"


def test_supports_native_capabilities_has_no_model_whitelist():
    from backend.modules.native_caps.registry import supports_native_capabilities

    assert supports_native_capabilities("deepseek", "deepseek-v4-pro") is True
    assert supports_native_capabilities("deepseek", "any-model") is True
    assert supports_native_capabilities("custom_openai", "ds-v4.1-flash") is True
    assert supports_native_capabilities("", "ds-v4.1-flash") is False


def test_file_id_cache_is_isolated_per_api_key():
    digest = "d" * 64
    first = native_files._cache_key("https://api.deepseek.com", "sk-a", digest, "user_data")
    second = native_files._cache_key("https://api.deepseek.com", "sk-b", digest, "user_data")

    assert first != second


def test_upload_falls_back_to_v1_files_for_relay(tmp_path, monkeypatch):
    """中转只暴露 /v1/files 时自动换路径并记住。"""
    native_files.clear_file_id_cache()
    path = _write(tmp_path / "contract.docx", b"docx")
    requested = []

    class FakeResponse:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self._payload = payload or {}
            self.text = ""

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def post(self, url, **_kwargs):
            requested.append(url)
            if url == "https://relay.example.com/files":
                return FakeResponse(404)
            return FakeResponse(200, {"id": "file-probe"})

    monkeypatch.setattr(native_files.httpx, "AsyncClient", FakeClient)

    file_id = asyncio.run(
        native_files.upload_file(
            api_base="https://relay.example.com/v1",
            api_key="test-placeholder",
            path=path,
            purpose="text_recognition",
        )
    )

    assert file_id == "file-probe"
    assert requested == [
        "https://relay.example.com/files",
        "https://relay.example.com/v1/files",
    ]
    assert native_files.upload_paths("https://relay.example.com")[0].endswith("/v1/files")
