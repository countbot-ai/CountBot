"""当前轮图片内容块与渠道媒体转存的回归测试。"""

import asyncio
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.agent.context import ContextBuilder
from backend.modules.channels.media_utils import promote_inbound_media
from backend.modules.media.image_blocks import (
    MAX_IMAGE_BYTES,
    build_image_blocks,
)
from backend.modules.providers.anthropic_provider import AnthropicProvider
from backend.modules.providers.media_capabilities import resolve_supports_image
from backend.modules.providers.openai_provider import OpenAIProvider

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAwMCAO5K3XcAAAAASUVORK5CYII="
)


def _write_image(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG_1X1)
    return path


def test_resolve_supports_image_prefers_explicit_override():
    assert resolve_supports_image(model="deepseek-chat", override=True) is True
    assert resolve_supports_image(model="glm-4.6v-flash", override=False) is False
    assert resolve_supports_image(model="glm-4.6v-flash") is True
    assert resolve_supports_image(model="qwen3-vl-plus") is True
    assert resolve_supports_image(model="claude-sonnet-4-6") is True
    assert resolve_supports_image(model="deepseek-v4.1-flash") is True
    assert resolve_supports_image(model="deepseek-chat") is False
    assert resolve_supports_image(model="unknown-text-model") is False


def test_build_image_blocks_reads_supported_images_only(tmp_path):
    workspace = tmp_path / "ws"
    _write_image(workspace / "uploads" / "chat" / "a.png")
    _write_image(workspace / "uploads" / "chat" / "b.bmp")
    outside = _write_image(tmp_path / "outside.png")

    result = build_image_blocks(
        ["uploads/chat/a.png", "uploads/chat/b.bmp", str(outside)],
        workspace=workspace,
    )

    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert block["type"] == "image"
    assert block["media_type"] == "image/png"
    assert block["data"] == base64.b64encode(PNG_1X1).decode("ascii")
    assert result.attached_paths == {"uploads/chat/a.png"}
    assert "uploads/chat/b.bmp" in result.skipped_paths
    # build_image_blocks 统一把路径归一化成 POSIX 形式，Windows 上 str(path) 带反斜杠
    assert outside.as_posix() in result.skipped_paths


def test_build_image_blocks_skips_oversized_image(tmp_path):
    workspace = tmp_path / "ws"
    oversized = workspace / "uploads" / "big.png"
    oversized.parent.mkdir(parents=True, exist_ok=True)
    with oversized.open("wb") as output:
        output.truncate(MAX_IMAGE_BYTES + 1)

    result = build_image_blocks(["uploads/big.png"], workspace=workspace)

    assert result.blocks == []
    assert result.skipped_paths == ["uploads/big.png"]


def test_context_builder_emits_image_blocks_for_capable_model(tmp_path):
    workspace = tmp_path / "ws"
    _write_image(workspace / "uploads" / "chat" / "a.png")
    builder = ContextBuilder(workspace=workspace)

    capable = builder._build_user_content(
        "看看这张图",
        ["uploads/chat/a.png"],
        supports_image=True,
    )
    assert isinstance(capable, list)
    assert capable[0]["type"] == "text"
    assert "attached directly" in capable[0]["text"]
    assert capable[1]["type"] == "image"

    text_only = builder._build_user_content(
        "看看这张图",
        ["uploads/chat/a.png"],
        supports_image=False,
    )
    assert isinstance(text_only, str)
    assert "uploads/chat/a.png" in text_only
    assert "workspace paths only" in text_only


def test_context_builder_appends_dynamic_text_to_block_content(tmp_path):
    workspace = tmp_path / "ws"
    _write_image(workspace / "uploads" / "chat" / "a.png")
    builder = ContextBuilder(workspace=workspace)

    messages = builder.build_messages(
        history=[],
        current_message="看看这张图",
        media=["uploads/chat/a.png"],
        supports_image=True,
    )

    user_content = messages[-1]["content"]
    assert isinstance(user_content, list)
    assert user_content[0]["type"] == "text"
    assert any(block["type"] == "image" for block in user_content)
    # 动态上下文仍追加在末尾，图片块位置不被后续文本覆盖。
    assert user_content[-1]["type"] == "text"


def test_openai_provider_converts_image_blocks_to_chat_parts():
    converted = OpenAIProvider._convert_content_blocks_for_chat_completions(
        [
            {"type": "text", "text": "hi"},
            {"type": "image", "media_type": "image/png", "data": "QUJD"},
        ]
    )

    assert converted == [
        {"type": "text", "text": "hi"},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,QUJD"},
        },
    ]


def test_openai_provider_adds_placeholder_when_stripping_images():
    request_params = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "hi"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,QUJD"},
                    },
                ],
            }
        ]
    }

    assert OpenAIProvider._strip_multimodal_image_content(request_params) is True
    content = request_params["messages"][0]["content"]
    assert "hi" in content
    assert "image(s) omitted" in content


def test_anthropic_provider_converts_image_blocks():
    converted = AnthropicProvider._convert_user_content_blocks(
        [
            {"type": "text", "text": "hi"},
            {"type": "image", "media_type": "image/png", "data": "QUJD"},
        ]
    )

    assert converted == [
        {"type": "text", "text": "hi"},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": "QUJD",
            },
        },
    ]


def test_promote_inbound_media_copies_to_durable_uploads(tmp_path):
    workspace = tmp_path / "ws"
    source = _write_image(
        workspace / "temp" / "channels" / "feishu" / "inbound" / "photo.png"
    )

    result = asyncio.run(
        promote_inbound_media(
            "feishu",
            [str(source)],
            account_id="default",
            workspace=workspace,
        )
    )

    assert len(result.media_paths) == 1
    stored = result.media_paths[0]
    assert stored.startswith("uploads/channels/feishu/default/")
    assert (workspace / stored).is_file()
    assert source.is_file()
    assert result.attachment_items[0]["path"] == stored
    assert result.attachment_items[0]["kind"] == "image"


def test_promote_inbound_media_keeps_existing_uploads(tmp_path):
    workspace = tmp_path / "ws"
    source = _write_image(workspace / "uploads" / "channels" / "wecom" / "a.png")

    result = asyncio.run(
        promote_inbound_media(
            "wecom",
            [str(source)],
            account_id="default",
            workspace=workspace,
        )
    )

    assert result.media_paths == ["uploads/channels/wecom/a.png"]
    assert len(result.attachment_items) == 1


def test_promote_inbound_media_leaves_outside_paths_unchanged(tmp_path):
    workspace = tmp_path / "ws"
    outside = _write_image(tmp_path / "outside.png")

    result = asyncio.run(
        promote_inbound_media(
            "dingtalk",
            [str(outside)],
            account_id="default",
            workspace=workspace,
        )
    )

    assert result.media_paths == [str(outside)]
    assert result.attachment_items == []
