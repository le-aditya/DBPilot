"""Seed the public demo project. PRD section 14.3.

A visitor should be able to see DBPilot working without creating an account or
finding a CSV, so the demo owns a small, genuinely relational dataset: customers
in cities, orders against them, products, and a junction table so the ER diagram
has an N:M edge to draw.

Idempotent: re-running replaces the demo project rather than accumulating copies.

Usage (from backend/):
    python scripts/seed_demo.py
    python scripts/seed_demo.py --email demo@dbpilot.app --password ...
"""

import argparse
import asyncio
import random
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.engine import create_engine
from app.models import Project, SourceType, User
from app.services.inference import ColumnType
from app.services.ingestion import ColumnSpec, ForeignKeySpec, TableSpec, commit_upload
from app.services.projects import delete_project

DEMO_EMAIL = "demo@dbpilot.local"
DEMO_PASSWORD = "demo-account-please-change"
PROJECT_NAME = "Northwind Lite"

CITIES = ["London", "Mumbai", "Berlin", "Toronto", "Sydney", "Chennai"]
FIRST = ["Ada", "Grace", "Alan", "Katherine", "Edsger", "Barbara", "Tim", "Radia"]
LAST = ["Lovelace", "Hopper", "Turing", "Johnson", "Dijkstra", "Liskov", "Berners-Lee", "Perlman"]
PRODUCTS = [
    ("Espresso beans", "Grocery", "12.50"),
    ("Green tea", "Grocery", "8.00"),
    ("Notebook", "Stationery", "4.25"),
    ("Fountain pen", "Stationery", "22.00"),
    ("Desk lamp", "Home", "35.99"),
    ("Cable tidy", "Home", "6.75"),
]
TAGS = [("vip", "Spends the most"), ("new", "Joined this quarter"), ("dormant", "No recent orders")]


def _csv(rows: list[list[object]], header: list[str]) -> bytes:
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join("" if cell is None else str(cell) for cell in row))
    return ("\n".join(lines) + "\n").encode()


def build_files() -> dict[str, bytes]:
    random.seed(24)  # deterministic, so the demo is the same for everyone

    customers = [
        [n, f"{FIRST[n % len(FIRST)]} {LAST[(n * 3) % len(LAST)]}",
         CITIES[n % len(CITIES)], date(2024, 1, 1) + timedelta(days=n * 11)]
        for n in range(1, 25)
    ]
    products = [[n, name, category, price] for n, (name, category, price) in enumerate(PRODUCTS, 1)]
    tags = [[n, name, description] for n, (name, description) in enumerate(TAGS, 1)]

    orders = []
    order_id = 1
    for customer_id, *_ in customers:
        for _ in range(random.randint(0, 4)):
            orders.append([
                order_id,
                customer_id,
                random.randint(1, len(PRODUCTS)),
                random.randint(1, 5),
                f"{random.uniform(4, 300):.2f}",
                date(2024, 3, 1) + timedelta(days=random.randint(0, 250)),
                random.choice(["true", "false"]),
            ])
            order_id += 1

    customer_tags = [
        [customer_id, random.randint(1, len(TAGS))]
        for customer_id, *_ in customers
        if random.random() < 0.5
    ]

    return {
        "customers.csv": _csv(customers, ["id", "name", "city", "joined_on"]),
        "products.csv": _csv(products, ["id", "name", "category", "unit_price"]),
        "tags.csv": _csv(tags, ["id", "name", "description"]),
        "orders.csv": _csv(
            orders,
            ["id", "customer_id", "product_id", "quantity", "amount", "ordered_on", "shipped"],
        ),
        "customer_tags.csv": _csv(customer_tags, ["customer_id", "tag_id"]),
    }


def build_specs() -> list[TableSpec]:
    def column(name: str, type_: ColumnType, nullable: bool = False) -> ColumnSpec:
        return ColumnSpec(name=name, source_name=name, type=type_, nullable=nullable)

    return [
        TableSpec(
            name="customers",
            source_filename="customers.csv",
            primary_key="id",
            columns=(
                column("id", ColumnType.integer),
                column("name", ColumnType.text),
                column("city", ColumnType.text),
                column("joined_on", ColumnType.date),
            ),
        ),
        TableSpec(
            name="products",
            source_filename="products.csv",
            primary_key="id",
            columns=(
                column("id", ColumnType.integer),
                column("name", ColumnType.text),
                column("category", ColumnType.text),
                column("unit_price", ColumnType.numeric),
            ),
        ),
        TableSpec(
            name="tags",
            source_filename="tags.csv",
            primary_key="id",
            columns=(
                column("id", ColumnType.integer),
                column("name", ColumnType.text),
                column("description", ColumnType.text),
            ),
        ),
        TableSpec(
            name="orders",
            source_filename="orders.csv",
            primary_key="id",
            columns=(
                column("id", ColumnType.integer),
                column("customer_id", ColumnType.integer),
                column("product_id", ColumnType.integer),
                column("quantity", ColumnType.integer),
                column("amount", ColumnType.numeric),
                column("ordered_on", ColumnType.date),
                column("shipped", ColumnType.boolean),
            ),
            foreign_keys=(
                ForeignKeySpec("customer_id", "customers", "id"),
                ForeignKeySpec("product_id", "products", "id"),
            ),
        ),
        # Two foreign keys and nothing else, so the ERD draws one N:M edge.
        TableSpec(
            name="customer_tags",
            source_filename="customer_tags.csv",
            columns=(
                column("customer_id", ColumnType.integer),
                column("tag_id", ColumnType.integer),
            ),
            foreign_keys=(
                ForeignKeySpec("customer_id", "customers", "id"),
                ForeignKeySpec("tag_id", "tags", "id"),
            ),
        ),
    ]


async def seed(email: str, password: str) -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, password_hash=hash_password(password))
            session.add(user)
            await session.flush()
            print(f"Created demo account {email}")

        existing = await session.scalar(
            select(Project).where(
                Project.user_id == user.id, Project.name == PROJECT_NAME
            )
        )
        if existing is not None:
            await delete_project(session, existing)
            print("Removed the previous demo project")

        project = Project(
            user_id=user.id,
            name=PROJECT_NAME,
            source_type=SourceType.upload,
            is_demo=True,
        )
        session.add(project)
        await session.flush()

        committed = await commit_upload(session, project, build_specs(), build_files())
        await session.commit()

    await engine.dispose()

    print(f"Seeded {PROJECT_NAME} into {project.schema_name}:")
    for table in committed:
        print(f"  {table.name}: {table.row_count} rows")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default=DEMO_EMAIL)
    parser.add_argument("--password", default=DEMO_PASSWORD)
    args = parser.parse_args()
    await seed(args.email, args.password)


if __name__ == "__main__":
    asyncio.run(main())
