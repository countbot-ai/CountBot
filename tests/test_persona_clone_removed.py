"""性格克隆剥离的回归约束。"""

from backend.app import app


def _iter_routes():
    for route in app.routes:
        router = getattr(route, "original_router", None)
        for item in router.routes if router is not None else [route]:
            path = getattr(item, "path", "")
            if path:
                yield path


def test_no_clone_routes_registered():
    paths = list(_iter_routes())
    assert not any("persona_clone" in path or "persona_evolution" in path for path in paths)


def test_persona_config_has_no_clone_fields():
    from backend.modules.config.schema import PersonaConfig

    fields = set(PersonaConfig.model_fields)
    assert "session_memory" not in fields
    assert "cloned_personality_name" not in fields


def test_personality_model_has_no_clone_columns():
    from backend.models.personality import Personality

    columns = {column.name for column in Personality.__table__.columns}
    assert "mental_models" not in columns
    assert "combined_doc" not in columns
    assert "source_stats" not in columns


def test_context_builder_has_no_clone_hook():
    from backend.modules.agent.context import ContextBuilder

    assert not hasattr(ContextBuilder, "_cloned_personality_name")
