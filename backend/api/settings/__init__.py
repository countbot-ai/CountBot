"""Settings API：聚合 validators/models/runtime/core 等子模块并重新导出全部对外符号。"""

from backend.api.settings._router import router
from backend.api.settings.models import (
    ExternalCodingProfileCheckRequest,
    ExternalCodingProfileCheckResponse,
    ExternalCodingProfilePayload,
    ExternalCodingToolsConfigPayload,
    ExternalCodingToolsConfigResponse,
    HeartbeatConfigResponse,
    ImportSettingsRequest,
    InjectionConfigResponse,
    ModelConfigResponse,
    PersonaConfigResponse,
    ProviderConfigResponse,
    ProviderMetadataResponse,
    SecurityConfigResponse,
    SettingsResponse,
    TestConnectionRequest,
    TestConnectionResponse,
    UpdateSettingsRequest,
    WorkspaceConfigResponse,
)
from backend.api.settings.runtime import (
    _apply_saved_config_runtime,
    _hot_reload_workspace_runtime,
    _prepare_message_handler_reload_params,
    _rebuild_shared_tool_registry_runtime,
    _reload_cron_runtime,
    _reload_injection_runtime,
    _validate_workspace_path_or_raise,
)
from backend.api.settings.validators import (
    _coerce_boolean_value,
    _heartbeat_plan_settings_changed,
    _list_enabled_channel_account_ids,
    _normalize_api_mode_value,
    _normalize_pattern_list,
    _validate_and_normalize_heartbeat_settings,
    _validate_cron_schedule_or_raise,
    _validate_regex_patterns_or_raise,
)

# 导入路由模块以完成 @router.xxx 注册（副作用导入，不能省略）
from backend.api.settings import core as _core  # noqa: F401
from backend.api.settings import external_coding as _external_coding  # noqa: F401
from backend.api.settings import connection_probe as _connection_probe  # noqa: F401
from backend.api.settings import transfer as _transfer  # noqa: F401
from backend.api.settings import provider_models as _provider_models  # noqa: F401
from backend.api.settings import workspace as _workspace  # noqa: F401

from backend.api.settings.core import (
    get_available_providers,
    get_dangerous_patterns,
    get_settings,
    update_settings,
)
from backend.api.settings.external_coding import (
    check_external_coding_tool_profile,
    get_external_coding_tools_config,
    update_external_coding_tools_config,
)
from backend.api.settings.connection_probe import test_connection
from backend.api.settings.transfer import (
    _deep_merge,
    export_settings,
    import_settings,
)
from backend.api.settings.workspace import (
    clean_temp_files,
    get_workspace_info,
    select_directory,
    set_workspace_path,
)
from backend.api.settings.provider_models import (
    add_provider_models,
    delete_provider_model,
    get_provider_model_catalog,
    reorder_provider_models,
    test_provider_connection,
    update_provider_model,
)

__all__ = [
    "router",
    "SettingsResponse",
    "UpdateSettingsRequest",
    "TestConnectionRequest",
    "TestConnectionResponse",
    "ImportSettingsRequest",
    "ExternalCodingProfilePayload",
    "ExternalCodingToolsConfigPayload",
    "ExternalCodingToolsConfigResponse",
    "ExternalCodingProfileCheckRequest",
    "ExternalCodingProfileCheckResponse",
    "get_settings",
    "update_settings",
    "get_dangerous_patterns",
    "get_available_providers",
    "get_external_coding_tools_config",
    "update_external_coding_tools_config",
    "check_external_coding_tool_profile",
    "test_connection",
    "get_provider_model_catalog",
    "add_provider_models",
    "update_provider_model",
    "delete_provider_model",
    "reorder_provider_models",
    "test_provider_connection",
    "select_directory",
    "get_workspace_info",
    "clean_temp_files",
    "set_workspace_path",
    "export_settings",
    "import_settings",
]
