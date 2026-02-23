"""配置加载器"""

import json
from typing import Any

from loguru import logger
from sqlalchemy import select

from backend.database import AsyncSessionLocal
from backend.models.setting import Setting
from backend.modules.config.schema import AppConfig


class ConfigLoader:
    """配置加载器"""

    def __init__(self) -> None:
        self.config: AppConfig = AppConfig()

    async def load(self) -> AppConfig:
        """从数据库加载配置"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Setting).where(Setting.key.like("config.%"))
            )
            settings = result.scalars().all()

            if not settings:
                logger.info("未找到配置，使用默认配置")
                await self.save()
                return self.config

            config_dict: dict[str, Any] = {}
            for setting in settings:
                key_path = setting.key.replace("config.", "")
                value = json.loads(setting.value)
                
                if value is None and "api_key" in key_path:
                    value = ""
                
                self._set_nested_value(config_dict, key_path, value)
            
            if "providers" in config_dict:
                for provider_name, provider_data in config_dict["providers"].items():
                    if isinstance(provider_data, dict) and provider_data.get("api_key") is None:
                        provider_data["api_key"] = ""

            self.config = AppConfig(**config_dict)
            
            # 如果启用了加密，解密 API 密钥
            if self.config.security.api_key_encryption_enabled:
                self._decrypt_api_keys()
                logger.info("API 密钥加密已启用")
            else:
                logger.warning("API 密钥加密未启用，建议在生产环境中启用")
            
            logger.info("配置加载完成")
            return self.config

    async def save(self) -> None:
        """保存配置到数据库"""
        async with AsyncSessionLocal() as session:
            config_dict = self.config.model_dump()
            
            # 如果启用了加密，加密 API 密钥
            if self.config.security.api_key_encryption_enabled:
                config_dict = self._encrypt_api_keys_in_dict(config_dict)
            
            await self._save_nested_dict(session, config_dict, "config")
            await session.commit()
            logger.info("配置保存完成")
    
    async def save_config(self, config: AppConfig) -> None:
        """保存配置"""
        self.config = config
        await self.save()

    async def _save_nested_dict(
        self, session: Any, data: dict[str, Any], prefix: str
    ) -> None:
        """递归保存嵌套字典"""
        for key, value in data.items():
            full_key = f"{prefix}.{key}"
            if isinstance(value, dict):
                await self._save_nested_dict(session, value, full_key)
            else:
                setting = Setting(key=full_key, value=json.dumps(value))
                await session.merge(setting)

    def _set_nested_value(self, data: dict[str, Any], key_path: str, value: Any) -> None:
        """设置嵌套字典值"""
        keys = key_path.split(".")
        current = data
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value

    async def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split(".")
        value = self.config
        for k in keys:
            value = getattr(value, k, None)
            if value is None:
                return default
        return value

    async def set(self, key: str, value: Any) -> None:
        """设置配置值"""
        keys = key.split(".")
        obj = self.config
        for k in keys[:-1]:
            obj = getattr(obj, k)
        setattr(obj, keys[-1], value)
        await self.save()
    
    def _decrypt_api_keys(self) -> None:
        """解密所有 provider 的 API 密钥"""
        from backend.modules.config.security import get_security_manager
        security_manager = get_security_manager()
        
        for provider_name, provider_config in self.config.providers.items():
            if provider_config.api_key:
                try:
                    decrypted = security_manager.decrypt(provider_config.api_key)
                    if decrypted:
                        provider_config.api_key = decrypted
                        logger.debug(f"解密 {provider_name} API 密钥")
                except Exception as e:
                    logger.warning(f"解密 {provider_name} API 密钥失败: {e}")
    
    def _encrypt_api_keys_in_dict(self, config_dict: dict[str, Any]) -> dict[str, Any]:
        """加密配置字典中的 API 密钥"""
        from backend.modules.config.security import get_security_manager
        security_manager = get_security_manager()
        
        if "providers" in config_dict:
            for provider_name, provider_data in config_dict["providers"].items():
                if isinstance(provider_data, dict) and provider_data.get("api_key"):
                    try:
                        encrypted = security_manager.encrypt(provider_data["api_key"])
                        if encrypted:
                            provider_data["api_key"] = encrypted
                            logger.debug(f"加密 {provider_name} API 密钥")
                    except Exception as e:
                        logger.warning(f"加密 {provider_name} API 密钥失败: {e}")
        return config_dict


config_loader = ConfigLoader()
