"""模型连通性测试。"""

from loguru import logger

from backend.modules.config.loader import config_loader
from backend.modules.config.schema import resolve_stream_enabled
from backend.modules.providers import create_provider
from backend.modules.providers.connection_test import run_connection_test
from backend.modules.providers.registry import get_provider_metadata

from backend.api.settings._router import router
from backend.api.settings.validators import (
    _normalize_api_mode_value,
    _normalize_api_type_value,
)
from backend.api.settings.models import (
    TestConnectionRequest,
    TestConnectionResponse,
)


@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_connection(request: TestConnectionRequest) -> TestConnectionResponse:
    """按请求参数或已保存的供应商配置发起一次最小流式请求。"""
    logger.info(f"Testing connection to {request.provider} with model {request.model}")

    provider_meta = get_provider_metadata(request.provider)
    if not provider_meta:
        return TestConnectionResponse(
            success=False,
            error=f"未知的 provider: {request.provider}",
        )

    test_model = (request.model or provider_meta.default_model or "").strip()
    test_api_base = request.api_base or provider_meta.default_api_base

    if not test_model:
        return TestConnectionResponse(
            success=False,
            error="请先填写模型名称，再测试连接。",
        )

    # 协议优先级：请求显式指定 > 已保存的供应商配置 > provider 默认
    saved_provider = config_loader.config.providers.get(request.provider)
    resolved_api_type = _normalize_api_type_value(
        request.api_type
        or getattr(saved_provider, "api_type", None)
        or None
    )

    logger.info(
        f"Using {provider_meta.name}, model: {test_model}, "
        f"base: {test_api_base}, api_type: {resolved_api_type}"
    )

    provider = create_provider(
        api_key=request.api_key,
        api_base=test_api_base,
        default_model=test_model,
        api_mode=_normalize_api_mode_value(None),
        api_type=resolved_api_type,
        timeout=30.0,
        max_retries=1,
        provider_id=request.provider,
        # 一次性探测不参与共享轮换，避免只测一个 Key 却改写全局轮换器
        enable_key_rotation=False,
        stream_enabled=resolve_stream_enabled(
            config_loader.config,
            request.provider,
            test_model,
            explicit=request.stream_enabled,
        ),
    )

    success, detail = await run_connection_test(
        provider,
        provider_id=request.provider,
        model=test_model,
        max_tokens=request.max_tokens or 0,
        temperature=request.temperature,
        thinking_enabled=request.thinking_enabled,
    )

    if success:
        return TestConnectionResponse(success=True, message=detail)
    return TestConnectionResponse(success=False, error=detail)
