"""ER diagram construction. Pure, so cardinality is tested exactly."""

from app.services.erd import Cardinality, build_erd
from app.services.introspection import (
    ColumnDescription,
    IndexDescription,
    TableDescription,
)


def col(name, data_type="text", *, pk=False, ref=None, nullable=False):
    return ColumnDescription(
        name=name,
        data_type=data_type,
        nullable=nullable,
        default=None,
        is_primary_key=pk,
        references_table=ref[0] if ref else None,
        references_column=ref[1] if ref else None,
    )


def tbl(name, *columns, rows=0, indexes=()):
    return TableDescription(
        name=name, row_count=rows, columns=columns, indexes=tuple(indexes)
    )


CUSTOMERS = tbl("customers", col("id", "bigint", pk=True), col("name"))
ORDERS = tbl(
    "orders",
    col("id", "bigint", pk=True),
    col("customer_id", "bigint", ref=("customers", "id")),
)


def test_every_table_becomes_a_node() -> None:
    erd = build_erd([CUSTOMERS, ORDERS])

    assert [node.name for node in erd.nodes] == ["customers", "orders"]


def test_a_node_carries_its_columns_and_key_flags() -> None:
    erd = build_erd([CUSTOMERS, ORDERS])

    orders = next(node for node in erd.nodes if node.name == "orders")
    flags = {c.name: (c.is_primary_key, c.is_foreign_key) for c in orders.columns}
    assert flags == {"id": (True, False), "customer_id": (False, True)}


def test_a_plain_foreign_key_is_one_to_many() -> None:
    erd = build_erd([CUSTOMERS, ORDERS])

    assert len(erd.edges) == 1
    edge = erd.edges[0]
    assert (edge.source, edge.target) == ("orders", "customers")
    assert edge.cardinality is Cardinality.one_to_many


def test_a_unique_foreign_key_is_one_to_one() -> None:
    """A unique index on the referencing column makes a second row impossible."""
    profiles = tbl(
        "profiles",
        col("id", "bigint", pk=True),
        col("customer_id", "bigint", ref=("customers", "id")),
        indexes=[
            IndexDescription(
                "profiles_customer_id_key",
                "CREATE UNIQUE INDEX profiles_customer_id_key ON profiles (customer_id)",
            )
        ],
    )

    erd = build_erd([CUSTOMERS, profiles])

    assert erd.edges[0].cardinality is Cardinality.one_to_one


def test_a_primary_key_foreign_key_is_one_to_one() -> None:
    settings = tbl(
        "settings", col("customer_id", "bigint", pk=True, ref=("customers", "id"))
    )

    erd = build_erd([CUSTOMERS, settings])

    assert erd.edges[0].cardinality is Cardinality.one_to_one


def test_a_junction_table_becomes_one_many_to_many_edge() -> None:
    tags = tbl("tags", col("id", "bigint", pk=True), col("label"))
    tagging = tbl(
        "customer_tags",
        col("customer_id", "bigint", ref=("customers", "id")),
        col("tag_id", "bigint", ref=("tags", "id")),
    )

    erd = build_erd([CUSTOMERS, tags, tagging])

    assert len(erd.edges) == 1
    edge = erd.edges[0]
    assert edge.cardinality is Cardinality.many_to_many
    assert {edge.source, edge.target} == {"customers", "tags"}
    assert edge.via == "customer_tags"


def test_a_junction_table_with_a_surrogate_key_is_still_a_junction() -> None:
    tags = tbl("tags", col("id", "bigint", pk=True))
    tagging = tbl(
        "customer_tags",
        col("id", "bigint", pk=True),
        col("customer_id", "bigint", ref=("customers", "id")),
        col("tag_id", "bigint", ref=("tags", "id")),
    )

    erd = build_erd([CUSTOMERS, tags, tagging])

    assert erd.edges[0].cardinality is Cardinality.many_to_many


def test_a_table_with_two_keys_and_its_own_data_is_not_a_junction() -> None:
    """An order line has a quantity, so it is an entity, not a crossing."""
    products = tbl("products", col("id", "bigint", pk=True))
    lines = tbl(
        "order_lines",
        col("order_id", "bigint", ref=("orders", "id")),
        col("product_id", "bigint", ref=("products", "id")),
        col("quantity", "integer"),
    )

    erd = build_erd([CUSTOMERS, ORDERS, products, lines])

    assert not any(e.cardinality is Cardinality.many_to_many for e in erd.edges)
    assert next(n for n in erd.nodes if n.name == "order_lines").is_junction is False


def test_a_self_referencing_pair_is_not_treated_as_a_crossing() -> None:
    follows = tbl(
        "follows",
        col("follower_id", "bigint", ref=("customers", "id")),
        col("followee_id", "bigint", ref=("customers", "id")),
    )

    erd = build_erd([CUSTOMERS, follows])

    assert all(edge.cardinality is not Cardinality.many_to_many for edge in erd.edges)
    assert len(erd.edges) == 2


def test_a_junction_node_is_still_returned_so_the_explorer_agrees() -> None:
    tags = tbl("tags", col("id", "bigint", pk=True))
    tagging = tbl(
        "customer_tags",
        col("customer_id", "bigint", ref=("customers", "id")),
        col("tag_id", "bigint", ref=("tags", "id")),
    )

    erd = build_erd([CUSTOMERS, tags, tagging])

    assert {node.name for node in erd.nodes} == {"customers", "tags", "customer_tags"}
    assert next(n for n in erd.nodes if n.name == "customer_tags").is_junction


def test_a_foreign_key_to_a_table_outside_the_diagram_is_dropped() -> None:
    orphan = tbl("orphan", col("missing_id", "bigint", ref=("elsewhere", "id")))

    erd = build_erd([orphan])

    assert erd.edges == ()


def test_an_empty_schema_is_an_empty_diagram() -> None:
    erd = build_erd([])

    assert erd.nodes == () and erd.edges == ()
