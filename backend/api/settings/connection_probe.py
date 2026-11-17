"""模型连通性测试。"""

from typing import Any, Dict

from fastapi import Depends, HTTPException, Request, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.modules.config.loader import config_loader
from backend.modules.config.schema import WorkspaceConfig
from backend.modules.providers.runtime import get_provider_runtime_state

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
    """
    测试 Provider 连接
    
    Args:
        request: 测试连接请求
        
    Returns:
        TestConnectionResponse: 测试结果
    """
    logger.info(f"Testing connection to {request.provider} with model {request.model}")
    
    try:
        from backend.modules.providers import create_provider
        from backend.modules.providers.registry import get_provider_metadata
        
        # 获取 provider 元数据
        provider_meta = get_provider_metadata(request.provider)
        if not provider_meta:
            return TestConnectionResponse(
                success=False,
                error=f"未知的 provider: {request.provider}",
            )
        
        # 使用用户提供的配置
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
        
        # 创建临时 provider
        provider = create_provider(
            api_key=request.api_key,
            api_base=test_api_base,
            default_model=test_model,
            api_mode=_normalize_api_mode_value(None),
            api_type=resolved_api_type,
            timeout=30.0,
            max_retries=1,
            provider_id=request.provider,
        )
        
        # 测试简单的聊天请求
        test_messages = [{"role": "user", "content": "Hello"}]
        
        response_received = False
        error_message = None
        response_content = ""
        
        request_kwargs: Dict[str, Any] = {
            "messages": test_messages,
            "tools": None,
            "model": test_model,
            "max_tokens": request.max_tokens or 0,
        }
        if request.temperature is not None and request.temperature > 0:
            request_kwargs["temperature"] = request.temperature
        if request.thinking_enabled is not None:
            request_kwargs["thinking_enabled"] = request.thinking_enabled

        async for chunk in provider.chat_stream(**request_kwargs):
            if chunk.error:
                error_message = chunk.error
                logger.error(f"Provider returned error: {chunk.error}")
                break
            
            if chunk.content:
                response_content += chunk.content
                response_received = True
            
            if chunk.finish_reason:
                logger.info(f"Stream finished with reason: {chunk.finish_reason}")
                response_received = True
                break
        
        if error_message:
            return TestConnectionResponse(
                success=False,
                error=error_message,
            )
        
        if response_received:
            logger.info(f"Connection test successful for {request.provider}")
            success_msg = f"Successfully connected to {request.provider}"
            if response_content:
                success_msg += f", received response: {response_content[:50]}"
            return TestConnectionResponse(
                success=True,
                message=success_msg,
            )
        else:
            return TestConnectionResponse(
                success=False,
                error="No response received from provider",
            )
        
    except Exception as e:
        logger.exception(f"Connection test failed: {e}")
        return TestConnectionResponse(
            success=False,
            error=str(e),
        )
