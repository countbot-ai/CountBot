"""音频转录 - 基于 Whisper 兼容 API"""

from typing import Optional

import httpx
from loguru import logger


class TranscriptionProvider:
    """Whisper 转录服务（支持 Groq / OpenAI）"""

    def __init__(self, api_key: str, provider: str = "groq"):
        self.api_key = api_key
        self.provider = provider

        if provider == "groq":
            self.api_base = "https://api.groq.com/openai/v1"
            self.model = "whisper-large-v3"
        elif provider == "openai":
            self.api_base = "https://api.openai.com/v1"
            self.model = "whisper-1"
        else:
            raise ValueError(f"不支持的转录服务: {provider}")

    async def transcribe(self, audio_file_path: str, language: Optional[str] = None) -> str:
        """转录音频文件为文本"""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                with open(audio_file_path, "rb") as audio_file:
                    files = {"file": (audio_file_path, audio_file, "audio/mpeg")}
                    data = {"model": self.model}
                    if language:
                        data["language"] = language

                    response = await client.post(
                        f"{self.api_base}/audio/transcriptions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        files=files,
                        data=data,
                    )
                    response.raise_for_status()
                    return response.json().get("text", "")

        except httpx.HTTPStatusError as e:
            logger.error(f"转录 API 错误: {e.response.status_code} - {e.response.text}")
            raise RuntimeError(f"转录失败: {e.response.text}") from e
        except Exception as e:
            logger.error(f"转录错误: {e}")
            raise
