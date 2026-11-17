"""DeepSeek 独立语音能力：ASR 与 TTS。"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import httpx
from loguru import logger

from .registry import normalize_deepseek_api_base

MAX_ASR_BYTES = 8 * 1024 * 1024
MAX_TTS_CHARS = 10000
SUPPORTED_ASR_SUFFIXES = {".wav", ".ogg", ".opus"}


class SpeechError(RuntimeError):
    """语音接口调用失败，status_code 供 API 层透传。"""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def _tools_url(api_base: Optional[str], name: str) -> str:
    return f"{normalize_deepseek_api_base(api_base)}/v1/tools/{name}"


def _auth_headers(api_key: str) -> Dict[str, str]:
    key = str(api_key or "").strip()
    if not key:
        raise SpeechError("缺少 DeepSeek API Key", status_code=400)
    return {"Authorization": f"Bearer {key}"}


async def _convert_to_wav(source: Path) -> Path:
    """把浏览器录音等格式转成 16k 单声道 16bit WAV。"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SpeechError("音频格式不受支持，且未安装 ffmpeg 无法转换", status_code=400)

    handle, raw_target = tempfile.mkstemp(prefix="countbot-asr-", suffix=".wav")
    os.close(handle)
    target = Path(raw_target)
    process = await asyncio.create_subprocess_exec(
        ffmpeg, "-y", "-i", str(source), "-ar", "16000", "-ac", "1",
        "-c:a", "pcm_s16le", str(target),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0 or not target.exists() or target.stat().st_size <= 0:
        target.unlink(missing_ok=True)
        detail = (stderr or b"").decode("utf-8", "ignore")[-300:]
        logger.warning(f"ASR 音频转换失败: {detail}")
        raise SpeechError("音频转换失败，请换一种格式重试", status_code=400)
    return target


async def transcribe_audio(
    *,
    api_base: Optional[str],
    api_key: str,
    path: Path,
    filename: Optional[str] = None,
) -> Dict[str, Any]:
    """调用 /v1/tools/asr，返回 {text, duration_ms, request_id}。"""
    source = Path(path)
    if not source.is_file():
        raise SpeechError("音频文件不存在", status_code=400)
    if source.stat().st_size > MAX_ASR_BYTES:
        raise SpeechError("音频超过 8 MiB 限制", status_code=413)

    working = source
    converted: Optional[Path] = None
    if source.suffix.lower() not in SUPPORTED_ASR_SUFFIXES:
        converted = await _convert_to_wav(source)
        working = converted

    try:
        size = working.stat().st_size
        if size > MAX_ASR_BYTES:
            raise SpeechError("音频超过 8 MiB 限制", status_code=413)
        upload_name = filename or working.name
        timeout = httpx.Timeout(180.0, connect=30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            with working.open("rb") as handle:
                response = await client.post(
                    _tools_url(api_base, "asr"),
                    headers=_auth_headers(api_key),
                    files={"file": (upload_name, handle, "application/octet-stream")},
                )
        if response.status_code >= 400:
            raise SpeechError(
                _extract_error(response), status_code=response.status_code
            )
        payload = response.json()
        text = str(payload.get("text") or "").strip()
        if not text:
            raise SpeechError("没有识别到语音内容", status_code=422)
        return {
            "text": text,
            "duration_ms": int(payload.get("duration_ms") or 0),
            "request_id": str(payload.get("request_id") or ""),
        }
    finally:
        if converted is not None:
            converted.unlink(missing_ok=True)


async def synthesize_speech(
    *,
    api_base: Optional[str],
    api_key: str,
    text: str,
    voice_id: str = "stella",
    audio_format: str = "wav",
) -> Tuple[bytes, str]:
    """调用 /v1/tools/tts，返回 (audio_bytes, media_type)。"""
    normalized = str(text or "").strip()
    if not normalized:
        raise SpeechError("没有可朗读的文本", status_code=400)
    if len(normalized) > MAX_TTS_CHARS:
        normalized = normalized[:MAX_TTS_CHARS]

    payload = {
        "text": normalized,
        "voice_id": voice_id if voice_id in ("stella", "tide") else "stella",
        "format": "pcm" if audio_format == "pcm" else "wav",
    }
    timeout = httpx.Timeout(180.0, connect=30.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                _tools_url(api_base, "tts"),
                headers={**_auth_headers(api_key), "Content-Type": "application/json"},
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", "ignore")
                    raise SpeechError(
                        _extract_error_text(body) or "语音合成失败",
                        status_code=response.status_code,
                    )
                chunks = [chunk async for chunk in response.aiter_bytes()]
        audio = b"".join(chunks)
        if not audio:
            raise SpeechError("语音合成返回空音频", status_code=502)
        media_type = "audio/pcm" if payload["format"] == "pcm" else "audio/wav"
        return audio, media_type
    except SpeechError:
        raise
    except Exception as exc:
        raise SpeechError(f"语音合成请求失败: {exc}", status_code=502) from exc


def _extract_error(response: httpx.Response) -> str:
    try:
        data = response.json()
    except Exception:
        return response.text[:300] or "语音识别失败"
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or "语音识别失败")
    return str(error or data)[:300]


def _extract_error_text(body: str) -> str:
    import json

    try:
        data = json.loads(body)
    except Exception:
        return ""
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or "")
    return ""
