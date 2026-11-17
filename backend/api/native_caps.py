"""模型原生能力目录与语音独立接口（ASR / TTS）。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.modules.config.loader import config_loader
from backend.modules.multiuser.identity import AuthUser
from backend.modules.multiuser.permissions import require_active_user
from backend.modules.native_caps import capability_catalog, normalize_native_capabilities
from backend.modules.native_caps.registry import supports_native_capabilities
from backend.modules.native_caps.speech import (
    SpeechError,
    synthesize_speech,
    transcribe_audio,
)

router = APIRouter(prefix="/api/native-caps", tags=["native-caps"])


class TtsRequest(BaseModel):
    provider_id: str = Field(..., description="供应商 ID，目前支持 deepseek")
    model: str = Field("", description="模型 ID，用于读取能力开关")
    text: str = Field(..., min_length=1)
    voice_id: str = Field("stella", description="stella / tide")
    format: str = Field("wav", description="wav / pcm")


@router.get("/catalog")
async def get_capability_catalog(
    provider_id: str = "",
    model: str = "",
    user: AuthUser = Depends(require_active_user),
) -> Dict[str, Any]:
    """前端高级设置使用的能力清单与当前模型支持状态。"""
    return {
        "capabilities": capability_catalog(),
        "provider_id": provider_id,
        "model": model,
        "supported": supports_native_capabilities(provider_id, model),
    }


async def _resolve_speech_config(
    user: AuthUser,
    provider_id: str,
    model: str,
    capability: str,
) -> Dict[str, Any]:
    provider_key = str(provider_id or "").strip()
    model_key = str(model or "").strip()
    if not provider_key:
        raise HTTPException(status_code=400, detail="缺少 provider_id")

    provider_config = None
    if getattr(user, "owner_id", None):
        from backend.modules.multiuser.effective import (
            ModelResolutionError,
            resolve_model_ref_for_user,
        )

        try:
            resolved = await resolve_model_ref_for_user(user, provider_key, model_key)
            provider_config = resolved.provider_config
        except ModelResolutionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        provider_config = config_loader.config.providers.get(provider_key)

    if provider_config is None:
        raise HTTPException(status_code=404, detail=f"供应商未配置: {provider_key}")

    entry = provider_config.find_model(model_key) if model_key else None
    caps = normalize_native_capabilities(
        getattr(entry, "native_capabilities", None) if entry else None
    )
    if capability == "asr" and not caps.asr:
        raise HTTPException(status_code=400, detail="当前模型未启用语音输入")
    if capability == "tts" and not caps.tts:
        raise HTTPException(status_code=400, detail="当前模型未启用语音朗读")

    keys = provider_config.get_effective_api_keys()
    api_key = keys[0] if keys else ""
    if not api_key:
        raise HTTPException(status_code=400, detail="供应商缺少 API Key")

    return {
        "api_key": api_key,
        "api_base": provider_config.api_base,
        "provider_id": provider_key,
        "model": model_key,
    }


@router.post("/speech/asr")
async def speech_to_text(
    file: UploadFile = File(...),
    provider_id: str = Form(...),
    model: str = Form(""),
    user: AuthUser = Depends(require_active_user),
) -> Dict[str, Any]:
    """上传录音并转写为文字。"""
    config = await _resolve_speech_config(user, provider_id, model, "asr")
    suffix = Path(file.filename or "audio.webm").suffix or ".webm"
    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(prefix="countbot-upload-", suffix=suffix, delete=False) as handle:
            temp_path = Path(handle.name)
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        result = await transcribe_audio(
            api_base=config["api_base"],
            api_key=config["api_key"],
            path=temp_path,
            filename=file.filename,
        )
        return result
    except SpeechError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    finally:
        await file.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


@router.post("/speech/tts")
async def text_to_speech(
    request: TtsRequest,
    user: AuthUser = Depends(require_active_user),
) -> Response:
    """把文本合成为音频并直接返回二进制。"""
    config = await _resolve_speech_config(
        user, request.provider_id, request.model, "tts"
    )
    try:
        audio, media_type = await synthesize_speech(
            api_base=config["api_base"],
            api_key=config["api_key"],
            text=request.text,
            voice_id=request.voice_id,
            audio_format=request.format,
        )
    except SpeechError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return Response(content=audio, media_type=media_type)
