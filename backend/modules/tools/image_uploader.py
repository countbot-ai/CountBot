"""图片上传服务 - 腾讯云 OSS"""

import hashlib
import hmac
from pathlib import Path
from datetime import datetime
from typing import Optional
from loguru import logger


class TencentOSSUploader:
    """腾讯云 OSS 上传器"""
    
    def __init__(self, secret_id: str, secret_key: str, bucket: str, region: str):
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.bucket = bucket
        self.region = region
        self.endpoint = f"https://{bucket}.cos.{region}.myqcloud.com"
    
    async def upload(self, file_path: Path) -> Optional[str]:
        """上传文件到腾讯云 OSS"""
        try:
            import aiohttp
            from urllib.parse import quote
            
            object_key = f"images/{file_path.name}"
            url = f"{self.endpoint}/{object_key}"
            
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            http_method = "PUT"
            http_uri = f"/{object_key}"
            
            current_time = int(datetime.now().timestamp())
            sign_time = f"{current_time};{current_time + 3600}"
            key_time = sign_time
            
            sign_key = hmac.new(
                self.secret_key.encode('utf-8'),
                sign_time.encode('utf-8'),
                hashlib.sha1
            ).hexdigest()
            
            http_string = f"{http_method.lower()}\n{http_uri}\n\n\n"
            
            sha1_http_string = hashlib.sha1(http_string.encode('utf-8')).hexdigest()
            string_to_sign = f"sha1\n{sign_time}\n{sha1_http_string}\n"
            
            signature = hmac.new(
                sign_key.encode('utf-8'),
                string_to_sign.encode('utf-8'),
                hashlib.sha1
            ).hexdigest()
            
            authorization = (
                f"q-sign-algorithm=sha1&"
                f"q-ak={self.secret_id}&"
                f"q-sign-time={sign_time}&"
                f"q-key-time={key_time}&"
                f"q-header-list=&"
                f"q-url-param-list=&"
                f"q-signature={signature}"
            )
            
            logger.info(f"上传到腾讯云 OSS: {file_path.name}")
            
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    url,
                    data=file_data,
                    headers={"Authorization": authorization}
                ) as response:
                    if response.status == 200:
                        logger.info(f"上传成功: {url}")
                        return url
                    else:
                        error_text = await response.text()
                        logger.error(f"上传失败 ({response.status}): {error_text}")
                        return None
            
        except Exception as e:
            logger.error(f"腾讯云 OSS 上传失败: {e}")
            return None


class ImageUploadManager:
    """图片上传管理器"""
    
    def __init__(self):
        self.uploader: Optional[TencentOSSUploader] = None
    
    def configure(self, secret_id: str, secret_key: str, bucket: str, region: str):
        """配置腾讯云 OSS"""
        self.uploader = TencentOSSUploader(secret_id, secret_key, bucket, region)
        logger.debug(f"腾讯云 OSS 已配置: {bucket} ({region})")
    
    async def upload(self, file_path: Path) -> Optional[str]:
        """上传文件到腾讯云 OSS"""
        if not self.uploader:
            logger.error("腾讯云 OSS 未配置")
            return None
        
        return await self.uploader.upload(file_path)
    
    async def upload_with_fallback(self, file_path: Path) -> Optional[str]:
        """上传文件（保持接口兼容性）"""
        return await self.upload(file_path)


_upload_manager: Optional[ImageUploadManager] = None


def get_upload_manager() -> ImageUploadManager:
    """获取全局图片上传管理器"""
    global _upload_manager
    if _upload_manager is None:
        _upload_manager = ImageUploadManager()
    return _upload_manager


def init_oss_uploader(config: dict | None = None):
    """初始化腾讯云 OSS 上传
    
    Args:
        config: 配置字典
            {
                "secret_id": "xxx",
                "secret_key": "xxx",
                "bucket": "xxx-appid",
                "region": "ap-guangzhou"
            }
    """
    manager = get_upload_manager()
    
    if not config:
        logger.warning("腾讯云 OSS 未配置")
        logger.info("QQ 等平台发送图片需要配置腾讯云 OSS")
        return
    
    required_keys = ["secret_id", "secret_key", "bucket", "region"]
    if not all(k in config for k in required_keys):
        logger.error(f"腾讯云 OSS 配置不完整，需要: {required_keys}")
        return
    
    manager.configure(
        secret_id=config["secret_id"],
        secret_key=config["secret_key"],
        bucket=config["bucket"],
        region=config["region"]
    )
    
    logger.debug("腾讯云 OSS 上传服务已初始化")
