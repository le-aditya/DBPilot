from app.db.base import Base
from app.models import (  # noqa: F401  (import registers the mappers)
    Connection,
    DiagramLayout,
    Explanation,
    Project,
    Query,
    RefreshToken,
    SavedQuery,
    SavedQueryVersion,
    Upload,
    User,
)

EXPECTED_TABLES = {
    "users",
    "projects",
    "connections",
    "uploads",
    "queries",
    "explanations",
    "saved_queries",
    "saved_query_versions",
    "refresh_tokens",
    "diagram_layouts",
}


def test_every_prd_table_is_mapped() -> None:
    assert set(Base.metadata.tables) == {f"dbpilot.{name}" for name in EXPECTED_TABLES}


def test_all_tables_live_in_the_dbpilot_schema() -> None:
    for table in Base.metadata.tables.values():
        assert table.schema == "dbpilot", f"{table.name} escaped the dbpilot schema"


def test_projects_are_unique_per_user_and_name() -> None:
    table = Base.metadata.tables["dbpilot.projects"]
    unique_column_sets = {
        tuple(sorted(c.name for c in constraint.columns))
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert ("name", "user_id") in unique_column_sets


def test_saved_queries_carry_a_template_and_parameters() -> None:
    """Design document §11 — parameterised saved queries are v1 scope."""
    table = Base.metadata.tables["dbpilot.saved_queries"]

    assert "sql_template" in table.columns
    assert "parameters" in table.columns
    assert table.columns["sql_template"].nullable is False


def test_projects_track_their_readonly_role() -> None:
    """Design document §16 — role cleanup on delete must not guess the role name."""
    table = Base.metadata.tables["dbpilot.projects"]

    assert "readonly_role" in table.columns
    assert "is_demo" in table.columns


def test_queries_records_the_denormalised_dashboard_columns() -> None:
    """Design document §5 — stored rather than recomputed, a documented trade-off."""
    table = Base.metadata.tables["dbpilot.queries"]

    assert "row_count" in table.columns
    assert "duration_ms" in table.columns
    assert table.columns["status"].nullable is False


def test_refresh_tokens_support_rotation_and_reuse_detection() -> None:
    """PRD F1 rotates refresh tokens on use; that needs revocation state."""
    table = Base.metadata.tables["dbpilot.refresh_tokens"]

    assert table.columns["jti"].unique is True
    assert table.columns["revoked_at"].nullable is True
    assert "replaced_by_jti" in table.columns
    assert table.columns["expires_at"].nullable is False
