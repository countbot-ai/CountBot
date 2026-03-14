"""配置加载器"""

import json
from typing import Any, Dict

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

            config_dict: Dict[str, Any] = {}
            for setting in settings:
                key_path = setting.key.replace("config.", "")
                value = json.loads(setting.value)
                
                if value is None and "api_key" in key_path:
                    value = ""
                
                self._set_nested_value(config_dict, key_path, value)
            
            if "providers" in config_dict:
                for provider_name, provider_data in config_dict["providers"].items():
                    if isinstance(provider_data, dict):
                        if provider_data.get("api_key") is None:
                            provider_data["api_key"] = ""
                        if "model" not in provider_data:
                            provider_data["model"] = None

            self.config = AppConfig(**config_dict)

            from backend.modules.workspace import workspace_manager
            workspace_path, used_fallback = workspace_manager.resolve_workspace_path_or_default(
                self.config.workspace.path
            )
            workspace_manager.activate_workspace_path(workspace_path)
            if used_fallback:
                self.config.workspace.path = str(workspace_path)
                logger.warning(
                    f"检测到无效工作空间配置，已在启动时回退到默认目录: {workspace_path}"
                )
            
            logger.info("配置加载完成")
            return self.config

    async def save(self) -> None:
        """保存配置到数据库"""
        async with AsyncSessionLocal() as session:
            config_dict = self.config.model_dump()
            await self._save_nested_dict(session, config_dict, "config")
            await session.commit()
            logger.info("配置保存完成")
    
    async def save_config(self, config: AppConfig) -> None:
        """保存配置"""
        normalized_config = config.model_copy(deep=True)
        workspace_path = None

        if normalized_config.workspace.path:
            from backend.modules.workspace import workspace_manager

            workspace_path = workspace_manager.prepare_workspace_path(
                normalized_config.workspace.path
            )
            normalized_config.workspace.path = str(workspace_path)

        previous_config = self.config
        self.config = normalized_config
        try:
            await self.save()
        except Exception:
            self.config = previous_config
            raise

        if workspace_path is not None:
            from backend.modules.workspace import workspace_manager

            workspace_manager.activate_workspace_path(workspace_path)

    async def _save_nested_dict(
        self, session: Any, data: Dict[str, Any], prefix: str
    ) -> None:
        """递归保存嵌套字典"""
        for key, value in data.items():
            full_key = f"{prefix}.{key}"
            if isinstance(value, dict):
                await self._save_nested_dict(session, value, full_key)
            else:
                setting = Setting(key=full_key, value=json.dumps(value))
                await session.merge(setting)

    def _set_nested_value(self, data: Dict[str, Any], key_path: str, value: Any) -> None:
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


config_loader = ConfigLoader()
