"""配置加载器"""

import json
from typing import Any, Dict

from loguru import logger
from sqlalchemy import select

from backend.database import AsyncSessionLocal
from backend.models.setting import Setting
from backend.modules.config.schema import AppConfig

# 旧默认值；升级后语义变为「不限制」，存量配置需迁移一次
LEGACY_DEFAULT_MAX_ITERATIONS = 25
# 迁移标记（独立于 config.* 命名空间）
MIGRATION_KEY_MAX_ITERATIONS = "migration.max_iterations_unlimited_v1"


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
                        if provider_data.get("api_keys") is None:
                            provider_data["api_keys"] = []
                        if "model" not in provider_data:
                            provider_data["model"] = None

            await self._migrate_legacy_max_iterations(session, config_dict)

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

    async def _migrate_legacy_max_iterations(
        self,
        session: Any,
        config_dict: Dict[str, Any],
    ) -> None:
        """把存量配置中的旧默认上限 25 一次性迁移为「不限制」。

        用独立 marker key 记录，迁移后用户再手动设 25 也不会被翻回。
        """
        model_cfg = config_dict.get("model")
        if not isinstance(model_cfg, dict):
            return
        if model_cfg.get("max_iterations") != LEGACY_DEFAULT_MAX_ITERATIONS:
            return

        marker = await session.get(Setting, MIGRATION_KEY_MAX_ITERATIONS)
        if marker is not None:
            return

        model_cfg["max_iterations"] = 0
        await session.merge(
            Setting(key="config.model.max_iterations", value=json.dumps(0))
        )
        await session.merge(
            Setting(key=MIGRATION_KEY_MAX_ITERATIONS, value=json.dumps(True))
        )
        await session.commit()
        logger.info(
            f"已将旧默认的工具调用上限 {LEGACY_DEFAULT_MAX_ITERATIONS} 迁移为「不限制」"
        )

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
