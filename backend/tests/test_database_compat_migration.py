"""回归测试：schema 兼容迁移机制可为旧表自动补齐缺失列。"""

import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, inspect

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.database import (
    CompatibilityColumnMigration,
    CompatibilityTableMigration,
    _apply_schema_compatibility_migrations,
)


def _create_legacy_sessions_table(conn) -> None:
    conn.exec_driver_sql(
        """
        CREATE TABLE sessions (
            id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            created_at DATETIME,
            updated_at DATETIME,
            summary VARCHAR(200),
            summary_updated_at DATETIME,
            last_summarized_msg_id INTEGER
        )
        """
    )


def _create_legacy_settings_table(conn) -> None:
    conn.exec_driver_sql(
        """
        CREATE TABLE settings (
            key VARCHAR PRIMARY KEY,
            value TEXT
        )
        """
    )


def _build_test_migrations() -> tuple[CompatibilityTableMigration, ...]:
    return (
        CompatibilityTableMigration(
            table_name="sessions",
            columns=(
                CompatibilityColumnMigration(
                    name="session_model_config",
                    ddl="session_model_config TEXT",
                ),
                CompatibilityColumnMigration(
                    name="session_persona_config",
                    ddl="session_persona_config TEXT",
                ),
                CompatibilityColumnMigration(
                    name="use_custom_config",
                    ddl="use_custom_config BOOLEAN DEFAULT 0",
                ),
            ),
        ),
        CompatibilityTableMigration(
            table_name="settings",
            columns=(
                CompatibilityColumnMigration(
                    name="updated_at",
                    ddl="updated_at DATETIME",
                ),
            ),
        ),
        CompatibilityTableMigration(
            table_name="missing_table",
            columns=(
                CompatibilityColumnMigration(
                    name="ignored_col",
                    ddl="ignored_col TEXT",
                ),
            ),
        ),
    )


def test_schema_compat_migration_adds_missing_columns() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "compat.db"
        engine = create_engine(f"sqlite:///{db_path}")
        migrations = _build_test_migrations()

        try:
            with engine.begin() as conn:
                _create_legacy_sessions_table(conn)
                _create_legacy_settings_table(conn)
                _apply_schema_compatibility_migrations(conn, migrations)

                session_columns = {
                    column["name"]
                    for column in inspect(conn).get_columns("sessions")
                }
                settings_columns = {
                    column["name"]
                    for column in inspect(conn).get_columns("settings")
                }
        finally:
            engine.dispose()

        expected = {
            "session_model_config",
            "session_persona_config",
            "use_custom_config",
        }
        missing = expected - session_columns
        if missing:
            raise AssertionError(f"缺少兼容迁移列: {sorted(missing)}")
        if "updated_at" not in settings_columns:
            raise AssertionError("settings.updated_at 未通过通用迁移补齐")


def test_schema_compat_migration_is_idempotent() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "compat.db"
        engine = create_engine(f"sqlite:///{db_path}")
        migrations = _build_test_migrations()

        try:
            with engine.begin() as conn:
                _create_legacy_sessions_table(conn)
                _create_legacy_settings_table(conn)
                _apply_schema_compatibility_migrations(conn, migrations)
                _apply_schema_compatibility_migrations(conn, migrations)

                columns = [
                    column["name"]
                    for column in inspect(conn).get_columns("sessions")
                ]
        finally:
            engine.dispose()

        if columns.count("session_model_config") != 1:
            raise AssertionError("session_model_config 列重复创建")
        if columns.count("session_persona_config") != 1:
            raise AssertionError("session_persona_config 列重复创建")
        if columns.count("use_custom_config") != 1:
            raise AssertionError("use_custom_config 列重复创建")


def main() -> int:
    tests = [
        ("add missing columns", test_schema_compat_migration_adds_missing_columns),
        ("idempotent rerun", test_schema_compat_migration_is_idempotent),
    ]

    failed = []
    for name, test_func in tests:
        try:
            test_func()
            print(f"✅ {name}")
        except Exception as exc:
            failed.append((name, exc))
            print(f"❌ {name}: {exc}")

    if failed:
        return 1

    print("\ndatabase compatibility migration tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())