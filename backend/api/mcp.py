from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from loguru import logger

from backend.modules.config.loader import config_loader
from backend.modules.config.schema import McpConfig, McpRegistryConfig, McpServerConfig
from backend.modules.mcp.exceptions import McpValidationError, McpServerNotFoundError
from backend.modules.mcp.validators import McpConfigValidator

router = APIRouter(prefix="/api/mcp", tags=["mcp"])

# 全局验证器实例
_validator = McpConfigValidator()


def _get_mcp_config() -> McpConfig:
    return config_loader.config.mcp


def _parse_claude_desktop_format(
    data: Dict[str, Any],
    existing_servers: list[McpServerConfig] | None = None,
) -> list[McpServerConfig]:
    servers = []
    mcp_servers = data.get("mcpServers", data)
    if not isinstance(mcp_servers, dict):
        return servers

    existing_enabled_map: Dict[str, bool] = {}
    if existing_servers:
        for s in existing_servers:
            if s.id or s.name:
                existing_enabled_map[s.id or s.name] = s.enabled

    for name, cfg in mcp_servers.items():
        if not isinstance(cfg, dict):
            continue
        enabled = existing_enabled_map.get(name, True)
        server = McpServerConfig(
            id=name,
            name=name,
            enabled=enabled,
            transport=None,
            command=cfg.get("command", ""),
            args=cfg.get("args", []),
            env=cfg.get("env", {}),
            url=cfg.get("url", ""),
            headers=cfg.get("headers", {}),
            timeout=cfg.get("toolTimeout", cfg.get("timeout", 30)),
            connect_timeout=cfg.get("connectTimeout", cfg.get("connect_timeout", 10)),
            include_tools=cfg.get("enabledTools", cfg.get("include_tools", ["*"])),
            enable_resources=cfg.get("enableResources", False),
            enable_prompts=cfg.get("enablePrompts", False),
        )
        servers.append(server)
    return servers


def _to_claude_desktop_format(servers: list[McpServerConfig]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for s in servers:
        name = s.name or s.id or "unknown"
        entry: Dict[str, Any] = {}
        if s.command:
            entry["command"] = s.command
        if s.args:
            entry["args"] = s.args
        if s.env:
            entry["env"] = s.env
        if s.url:
            entry["url"] = s.url
        if s.headers:
            entry["headers"] = s.headers
        if s.timeout != 30:
            entry["toolTimeout"] = s.timeout
        if s.include_tools and s.include_tools != ["*"]:
            entry["enabledTools"] = s.include_tools
        result[name] = entry
    return {"mcpServers": result}


@router.get("/overview")
async def get_overview():
    mcp = _get_mcp_config()
    servers = mcp.registry.servers
    enabled_servers = [s for s in servers if s.enabled]

    try:
        from backend.modules.mcp.client import McpClientManager
        manager = McpClientManager.get_instance()
        # 延迟连接：如果MCP已启用但未连接，自动触发连接
        if mcp.enabled and not manager.connected:
            await manager.ensure_connected()
        status = manager.get_status()
        connected_servers = status["servers"]
        connected_count = len(connected_servers)
        mcp_tool_count = status["tool_count"]
        server_status = status.get("server_status", {})
    except Exception:
        connected_servers = []
        connected_count = 0
        mcp_tool_count = 0
        server_status = {}

    server_items = []
    for s in servers:
        server_id = s.id or s.name or "unknown"
        is_connected = server_id in connected_servers
        s_status = server_status.get(server_id, {})
        # Get tool names for this server
        server_tools = []
        if is_connected:
            all_tools = status.get("tools", [])
            server_tools = [t for t in all_tools if t.startswith(f"mcp_{server_id}_")]
        server_items.append({
            "id": server_id,
            "name": s.name or server_id,
            "description": s.description,
            "enabled": s.enabled,
            "running": is_connected,
            "transport": s.transport or "auto",
            "tool_count": s_status.get("tool_count", 0),
            "tools": server_tools,
            "last_error": None,
        })

    return {
        "success": True,
        "enabled": mcp.enabled,
        "summary": {
            "total_servers": len(servers),
            "enabled_servers": len(enabled_servers),
            "connected_servers": connected_count,
            "mcp_tool_count": mcp_tool_count,
        },
        "servers": server_items,
    }


@router.get("/registry")
async def get_registry():
    mcp = _get_mcp_config()
    return {
        "version": mcp.registry.version,
        "servers": [s.model_dump() for s in mcp.registry.servers],
    }


@router.put("/registry")
async def update_registry(data: Dict[str, Any]):
    try:
        registry = McpRegistryConfig(**data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid registry data: {e}")

    # 验证整个注册表
    errors = _validator.validate_registry(registry.servers)
    if errors:
        raise HTTPException(status_code=400, detail=f"Registry validation failed: {'; '.join(errors[:3])}")

    config_loader.config.mcp.registry = registry

    try:
        await config_loader.save_config(config_loader.config)
        logger.info("MCP registry updated")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save config: {e}")

    if config_loader.config.mcp.enabled:
        try:
            from backend.modules.mcp.client import McpClientManager
            manager = McpClientManager.get_instance()
            await manager.disconnect()

            enabled_servers = [s for s in registry.servers if s.enabled]
            if enabled_servers:
                import asyncio
                task = asyncio.create_task(manager.connect(enabled_servers))
                # 添加错误回调
                def on_error(t):
                    if t.exception():
                        logger.error(f"Reconnect after registry update failed: {t.exception()}")
                task.add_done_callback(on_error)
        except ImportError:
            logger.debug("mcp package not installed, MCP reconnect deferred")
        except Exception as exc:
            logger.warning(f"Auto-reconnect after save failed: {exc}")

    return {
        "version": registry.version,
        "servers": [s.model_dump() for s in registry.servers],
    }


@router.post("/test")
async def test_server(data: Dict[str, Any]):
    try:
        server_config = McpServerConfig(**data.get("server", data))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid server config: {e}")

    # 验证配置
    errors = _validator.validate_server(server_config)
    if errors:
        return {"success": False, "message": f"Validation failed: {', '.join(errors)}"}

    try:
        from backend.modules.mcp.client import test_mcp_server
        result = await test_mcp_server(server_config)

        # 如果测试成功且 MCP 已启用，自动连接该服务器
        if result.get("success") and config_loader.config.mcp.enabled:
            try:
                from backend.modules.mcp.client import McpClientManager
                manager = McpClientManager.get_instance()
                server_id = server_config.id or server_config.name or "unknown"
                manager._server_configs[server_id] = server_config

                if server_id in manager._conn_tasks:
                    await manager.reconnect_server(server_id)
                else:
                    import asyncio
                    task = asyncio.create_task(manager.connect([server_config]))
                    # 添加错误回调
                    def on_error(t):
                        if t.exception():
                            logger.error(f"Auto-connect failed: {t.exception()}")
                    task.add_done_callback(on_error)
            except Exception as exc:
                logger.warning(f"Auto-connect after test failed: {exc}")

        return result
    except ImportError:
        return {"success": False, "message": "mcp package not installed, run: pip install mcp"}
    except Exception as e:
        logger.error(f"Test server failed: {e}")
        return {"success": False, "message": f"Test failed: {type(e).__name__}: {e}"}


@router.post("/toggle")
async def toggle_mcp(data: Dict[str, Any]):
    enabled = data.get("enabled", False)
    config_loader.config.mcp.enabled = enabled

    try:
        await config_loader.save_config(config_loader.config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save config: {e}")

    if enabled:
        servers = config_loader.config.mcp.registry.servers
        enabled_servers = [s for s in servers if s.enabled]
        if enabled_servers:
            try:
                from backend.modules.mcp.client import McpClientManager
                manager = McpClientManager.get_instance()

                import asyncio
                task = asyncio.create_task(manager.connect(enabled_servers))
                # 添加错误回调
                def on_error(t):
                    if t.exception():
                        logger.error(f"Connect on toggle failed: {t.exception()}")
                task.add_done_callback(on_error)
            except ImportError:
                logger.debug("mcp package not installed, MCP connection deferred")
            except Exception as exc:
                logger.warning(f"Auto-connect on toggle failed: {exc}")
    else:
        try:
            from backend.modules.mcp.client import McpClientManager
            manager = McpClientManager.get_instance()
            await manager.disconnect()
        except Exception as e:
            logger.warning(f"Disconnect on toggle failed: {e}")

    logger.info(f"MCP {'enabled' if enabled else 'disabled'}")
    return {"success": True, "enabled": enabled}


@router.post("/import")
async def import_config(data: Dict[str, Any]):
    format_type = data.get("format", "claude_desktop")
    raw = data.get("data", {})
    merge = data.get("merge", True)

    existing_servers = config_loader.config.mcp.registry.servers

    if format_type == "claude_desktop":
        new_servers = _parse_claude_desktop_format(raw, existing_servers)
    else:
        new_servers = [McpServerConfig(**s) for s in raw.get("servers", [])]

    if not new_servers:
        return {"success": False, "message": "No servers found in imported data"}

    existing_ids = {s.id or s.name for s in existing_servers}

    if merge:
        for s in new_servers:
            if s.id not in existing_ids and s.name not in existing_ids:
                config_loader.config.mcp.registry.servers.append(s)
    else:
        config_loader.config.mcp.registry.servers = new_servers

    try:
        await config_loader.save_config(config_loader.config)
        logger.info(f"MCP config imported: {len(new_servers)} servers (merge={merge})")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save config: {e}")

    return {
        "success": True,
        "imported": len(new_servers),
        "merged": merge,
        "servers": [s.model_dump() for s in config_loader.config.mcp.registry.servers],
    }


@router.get("/export")
async def export_config(format: str = "claude_desktop"):
    mcp = _get_mcp_config()
    servers = mcp.registry.servers

    if format == "claude_desktop":
        return _to_claude_desktop_format(servers)
    else:
        return {
            "version": mcp.registry.version,
            "servers": [s.model_dump() for s in servers],
        }


@router.post("/reconnect")
async def reconnect_server(data: Dict[str, Any] | None = None):
    server_id = None
    if data:
        server_id = data.get("server_id")
    try:
        from backend.modules.mcp.client import McpClientManager
        manager = McpClientManager.get_instance()
        # Ensure configs are loaded from registry before reconnecting
        mcp = _get_mcp_config()
        for s in mcp.registry.servers:
            sid = s.id or s.name or "unknown"
            manager._server_configs[sid] = s
        if server_id:
            success = await manager.reconnect_server(server_id)
            return {"success": success, "server_id": server_id}
        else:
            await manager.reconnect_all()
            return {"success": True}
    except ImportError:
        return {"success": False, "message": "mcp package not installed"}
    except Exception as e:
        return {"success": False, "message": f"Reconnect failed: {type(e).__name__}: {e}"}


@router.post("/start")
async def start_server(data: Dict[str, Any]):
    server_id = data.get("server_id")
    if not server_id:
        raise HTTPException(status_code=400, detail="server_id is required")

    mcp = _get_mcp_config()
    cfg = next((s for s in mcp.registry.servers if (s.id or s.name) == server_id), None)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found in registry")

    try:
        from backend.modules.mcp.client import McpClientManager
        manager = McpClientManager.get_instance()
        manager._server_configs[server_id] = cfg
        success = await manager.start_server(server_id)
        return {"success": success, "server_id": server_id}
    except ImportError:
        return {"success": False, "message": "mcp package not installed"}
    except Exception as e:
        return {"success": False, "message": f"Start failed: {type(e).__name__}: {e}"}


@router.post("/stop")
async def stop_server(data: Dict[str, Any]):
    server_id = data.get("server_id")
    if not server_id:
        raise HTTPException(status_code=400, detail="server_id is required")
    try:
        from backend.modules.mcp.client import McpClientManager
        manager = McpClientManager.get_instance()
        success = await manager.disconnect_server(server_id)
        return {"success": success, "server_id": server_id}
    except ImportError:
        return {"success": False, "message": "mcp package not installed"}
    except Exception as e:
        return {"success": False, "message": f"Stop failed: {type(e).__name__}: {e}"}


@router.get("/status/{server_id}")
async def get_server_status(server_id: str):
    try:
        from backend.modules.mcp.client import McpClientManager
        manager = McpClientManager.get_instance()
        status = manager.get_status()
        server_status = status.get("server_status", {}).get(server_id)
        if server_status is None:
            return {"success": False, "message": f"Server '{server_id}' not found"}
        all_tools = status.get("tools", [])
        server_tools = [t for t in all_tools if t.startswith(f"mcp_{server_id}_")]
        return {
            "success": True,
            "server_id": server_id,
            "connected": server_status.get("connected", False),
            "transport": server_status.get("transport", "auto"),
            "tool_count": server_status.get("tool_count", 0),
            "tools": server_tools,
        }
    except ImportError:
        return {"success": False, "message": "mcp package not installed"}
    except Exception as e:
        logger.error(f"Get server status failed: {e}")
        return {"success": False, "message": f"Status check failed: {type(e).__name__}: {e}"}
