"""音频 API 端点（实现中）"""

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from loguru import logger
from typing import Optional
import tempfile
import os

from backend.modules.providers.transcription import TranscriptionProvider

router = APIRouter(prefix="/api/audio", tags=["audio"])

# Initialize transcription provider
transcription_provider: Optional[TranscriptionProvider] = None


def init_transcription_provider(api_key: str, provider: str = "groq"):
    """初始化转录服务提供者"""
    global transcription_provider
    try:
        transcription_provider = TranscriptionProvider(api_key=api_key, provider=provider)
        logger.info(f"Transcription provider initialized: {provider}")
    except Exception as e:
        logger.error(f"Failed to initialize transcription provider: {e}")
        transcription_provider = None


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(..., description="Audio file to transcribe")
):
    """转录音频文件为文本（支持 mp3/mp4/wav/webm 等格式，最大 25MB）"""
    if not transcription_provider:
        raise HTTPException(
            status_code=503,
            detail="Transcription service not configured. Please set up Whisper API key in settings."
        )
    
    # 验证文件类型
    allowed_types = ["audio/mpeg", "audio/mp4", "audio/wav", "audio/webm", "audio/x-m4a"]
    allowed_extensions = [".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"]
    
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # 验证文件大小（25MB 限制）
    max_size = 25 * 1024 * 1024
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: 25MB"
        )
    
    try:
        # 保存到临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name
        
        try:
            # 转录
            logger.info(f"Transcribing audio file: {file.filename} ({len(content)} bytes)")
            text = await transcription_provider.transcribe(temp_path)
            
            logger.info(f"Transcription successful: {len(text)} characters")
            return JSONResponse(content={
                "text": text,
                "filename": file.filename,
                "size": len(content)
            })
        
        finally:
            # 清理临时文件
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Transcription failed: {str(e)}"
        )


@router.get("/status")
async def get_transcription_status():
    """获取转录服务状态"""
    return JSONResponse(content={
        "available": transcription_provider is not None,
        "provider": transcription_provider.provider if transcription_provider else None
    })
