"""Seed a full Northwind-style dataset into an existing DBPilot account.

The demo project in ``seed_demo.py`` is deliberately small. This one is the
classic Northwind shape — customers, orders and order details, products with
categories and suppliers, employees with territories, shippers — so a demo can
show joins, aggregates, an N:M junction and a self-referencing hierarchy.

Deterministic: re-running replaces the project rather than accumulating copies.

Usage (from backend/):
    python scripts/seed_northwind.py --email you@gmail.com
    python scripts/seed_northwind.py --email you@gmail.com --password ...
"""

import argparse
import asyncio
import csv
import io
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

DEMO_EMAIL = "demo@dbpilot.app"
DEMO_PASSWORD = "demo-account-please-change"
PROJECT_NAME = "Northwind"

CATEGORIES = [
    "Beverages",
    "Condiments",
    "Confections",
    "Dairy Products",
    "Grains/Cereals",
    "Meat/Poultry",
    "Produce",
    "Seafood",
]

SUPPLIERS = [
    ("Exotic Liquids", "Charlotte Cooper", "London", "UK", "(171) 555-2222"),
    ("New Orleans Cajun Delights", "Shelley Burke", "New Orleans", "USA", "(100) 555-4822"),
    ("Grandma Kelly's Homestead", "Regina Murphy", "Ann Arbor", "USA", "(313) 555-5735"),
    ("Tokyo Traders", "Yoshi Nagase", "Tokyo", "Japan", "(03) 3555-5011"),
    ("Cooperativa de Quesos Las Cabras", "Antonio del Valle", "Oviedo", "Spain", "(98) 598 76 54"),
    ("Pavlova Ltd.", "Ian Devling", "Melbourne", "Australia", "(03) 444-2343"),
    ("Plutzer Lebensmittelgrossmarkte AG", "Peter Wilson", "Frankfurt", "Germany", "(069) 992755"),
    ("Specialty Biscuits Ltd.", "Marie Delamare", "London", "UK", "(171) 555-7555"),
    ("PB Knackebrod AB", "Eliane Noz", "Goteborg", "Sweden", "(031) 335 06 00"),
    ("Refrescos Americanas LTDA", "Carlos Diaz", "Sao Paulo", "Brazil", "(11) 555 4640"),
    ("Heli Susswaren GmbH", "Beate Vileid", "Bremen", "Germany", "(0421) 555-7374"),
    ("Ma Maison", "Jean-Guy Lauzon", "Montreal", "Canada", "(514) 555-2955"),
]

CUSTOMERS = [
    ("Alfreds Futterkiste", "Maria Anders", "Berlin", "Germany", "030-0074321"),
    ("Ana Trujillo Emparedados y helados", "Ana Trujillo", "Mexico City", "Mexico", "(5) 555-4729"),
    ("Antonio Moreno Taqueria", "Antonio Moreno", "Mexico City", "Mexico", "(5) 555-3932"),
    ("Around the Horn", "Thomas Hardy", "London", "UK", "(171) 555-7788"),
    ("Berglunds snabbkop", "Christina Berglund", "Lulea", "Sweden", "0921-12 34 65"),
    ("Blauer See Delikatessen", "Hanna Moos", "Mannheim", "Germany", "0621-08460"),
    ("Bottom-Dollar Markets", "Elizabeth Lincoln", "Tsawassen", "Canada", "(604) 555-4729"),
    ("Cactus Comidas para llevar", "Patricio Simpson", "Buenos Aires", "Argentina", "(1) 135-5555"),
    ("Centro comercial Moctezuma", "Francisco Chang", "Mexico City", "Mexico", "(5) 555-3392"),
    ("Chop-suey Chinese", "Yang Wang", "Bern", "Switzerland", "0452-076545"),
    ("Comercio Mineiro", "Pedro Afonso", "Sao Paulo", "Brazil", "(11) 555-7647"),
    ("Consolidated Holdings", "Elizabeth Brown", "London", "UK", "(171) 555-2282"),
    ("Drachenblut Delikatessen", "Sven Ottlieb", "Aachen", "Germany", "0241-039123"),
    ("Du monde entier", "Janine Labrune", "Nantes", "France", "40.67.88.88"),
    ("Eastern Connection", "Ann Devon", "London", "UK", "(171) 555-0297"),
    ("Ernst Handel", "Roland Mendel", "Graz", "Austria", "7675-3425"),
    ("Familia Arquibaldo", "Aria Cruz", "Sao Paulo", "Brazil", "(11) 555-9857"),
    ("FISSA Fabrica Inter. Salchichas", "Diego Roel", "Madrid", "Spain", "(91) 555 94 44"),
    ("Folies gourmandes", "Martine Rance", "Lille", "France", "20.16.10.16"),
    ("Folk och fa HB", "Maria Larsson", "Bracke", "Sweden", "0695-34 67 21"),
    ("Galería del gastronomo", "Eduardo Saavedra", "Barcelona", "Spain", "(93) 203 4560"),
    ("Godos Cocina Típica", "Jose Pedro Freyre", "Sevilla", "Spain", "(95) 555 82 82"),
    ("Gourmet Lanchonetes", "Andre Fonseca", "Campinas", "Brazil", "(11) 555-9482"),
    ("Great Lakes Food Market", "Howard Snyder", "Eugene", "USA", "(503) 555-7555"),
]

PRODUCTS = [
    ("Chai", 1, 1, "18.00"),
    ("Chang", 1, 1, "19.00"),
    ("Aniseed Syrup", 2, 1, "10.00"),
    ("Chef Anton's Cajun Seasoning", 2, 2, "22.00"),
    ("Chef Anton's Gumbo Mix", 2, 2, "21.35"),
    ("Grandma's Boysenberry Spread", 2, 3, "25.00"),
    ("Uncle Bob's Organic Dried Pears", 7, 3, "30.00"),
    ("Northwoods Cranberry Sauce", 2, 3, "40.00"),
    ("Mishi Kobe Niku", 6, 4, "97.00"),
    ("Ikura", 8, 4, "31.00"),
    ("Queso Cabrales", 4, 5, "21.00"),
    ("Queso Manchego La Pastora", 4, 5, "38.00"),
    ("Konbu", 8, 4, "6.00"),
    ("Tofu", 7, 4, "23.25"),
    ("Genen Shouyu", 2, 4, "15.50"),
    ("Pavlova", 3, 6, "17.45"),
    ("Alice Mutton", 6, 7, "39.00"),
    ("Carnarvon Tigers", 8, 7, "62.50"),
    ("Teatime Chocolate Biscuits", 3, 8, "9.20"),
    ("Sir Rodney's Marmalade", 3, 8, "81.00"),
    ("Sir Rodney's Scones", 3, 8, "10.00"),
    ("Gustaf's Knackebrod", 5, 9, "21.00"),
    ("Tunnbrod", 5, 9, "9.00"),
    ("Guijarrelo", 4, 5, "39.00"),
    ("NuNuCa Nuss-Nougat-Creme", 3, 10, "14.00"),
    ("Gumbar Gummibarchen", 3, 10, "31.23"),
    ("Schoggi Schokolade", 3, 10, "43.90"),
    ("Rossle Sauerkraut", 7, 11, "45.60"),
    ("Thuringer Rostbratwurst", 6, 11, "123.79"),
    ("Nord-Ost Matjeshering", 8, 12, "25.89"),
]

REGIONS = ["Eastern", "Western", "Northern", "Southern"]

TERRITORIES = [
    ("Boston", 1),
    ("New York", 1),
    ("Philadelphia", 1),
    ("Washington", 1),
    ("Atlanta", 1),
    ("Savannah", 1),
    ("Chicago", 2),
    ("Dallas", 2),
    ("Denver", 2),
    ("Los Angeles", 3),
    ("San Francisco", 3),
    ("Seattle", 2),
]

EMPLOYEES = [
    ("Nancy", "Davolio", "Sales Representative", "Seattle", "USA", None),
    ("Andrew", "Fuller", "Vice President Sales", "Tacoma", "USA", None),
    ("Janet", "Leverling", "Sales Representative", "Kirkland", "USA", 2),
    ("Margaret", "Peacock", "Sales Representative", "Redmond", "USA", 2),
    ("Steven", "Buchanan", "Sales Manager", "London", "UK", 2),
    ("Michael", "Suyama", "Sales Representative", "London", "UK", 5),
    ("Robert", "King", "Sales Representative", "London", "UK", 5),
    ("Laura", "Callahan", "Inside Sales Coordinator", "Seattle", "USA", 2),
    ("Anne", "Dodsworth", "Sales Representative", "London", "UK", 5),
]

SHIPPERS = [
    ("Speedy Express", "(503) 555-9831"),
    ("United Package", "(503) 555-3199"),
    ("Federal Shipping", "(503) 555-9931"),
]


def _csv(rows: list[list[object]], header: list[str]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode()


def build_files() -> dict[str, bytes]:
    random.seed(7)

    regions = [[number, name] for number, name in enumerate(REGIONS, 1)]
    territories = [[number, name, region] for number, (name, region) in enumerate(TERRITORIES, 1)]
    employees = [
        [number, first, last, title, city, country, reports_to]
        for number, (first, last, title, city, country, reports_to) in enumerate(EMPLOYEES, 1)
    ]
    employee_territories = []
    for employee_id in range(1, len(EMPLOYEES) + 1):
        for territory_id in random.sample(range(1, len(TERRITORIES) + 1), k=3):
            employee_territories.append([employee_id, territory_id])

    categories = [
        [number, name, f"{name} items for the Northwind catalog"]
        for number, name in enumerate(CATEGORIES, 1)
    ]
    suppliers = [
        [number, *supplier] for number, supplier in enumerate(SUPPLIERS, 1)
    ]
    shippers = [[number, *shipper] for number, shipper in enumerate(SHIPPERS, 1)]
    customers = [[number, *customer] for number, customer in enumerate(CUSTOMERS, 1)]

    products = []
    for number, (name, category_id, supplier_id, price) in enumerate(PRODUCTS, 1):
        products.append(
            [
                number,
                name,
                category_id,
                supplier_id,
                price,
                random.randint(0, 120),
                random.choice(["true", "false"]),
            ]
        )

    orders = []
    order_details = []
    for order_id in range(1, 61):
        ordered_on = date(2024, 1, 1) + timedelta(days=random.randint(0, 300))
        orders.append(
            [
                order_id,
                random.randint(1, len(CUSTOMERS)),
                random.randint(1, len(EMPLOYEES)),
                ordered_on.isoformat(),
                random.randint(1, len(SHIPPERS)),
                f"{random.uniform(2, 250):.2f}",
            ]
        )
        for product_id in random.sample(range(1, len(PRODUCTS) + 1), k=random.randint(1, 4)):
            order_details.append(
                [
                    order_id,
                    product_id,
                    PRODUCTS[product_id - 1][3],
                    random.randint(1, 20),
                    random.choice(["0.00", "0.05", "0.10", "0.15", "0.20"]),
                ]
            )

    return {
        "region.csv": _csv(regions, ["id", "region_description"]),
        "territories.csv": _csv(
            territories, ["id", "territory_description", "region_id"]
        ),
        "employees.csv": _csv(
            employees,
            ["id", "first_name", "last_name", "title", "city", "country", "reports_to"],
        ),
        "employee_territories.csv": _csv(
            employee_territories, ["employee_id", "territory_id"]
        ),
        "categories.csv": _csv(categories, ["id", "category_name", "description"]),
        "suppliers.csv": _csv(
            suppliers, ["id", "company_name", "contact_name", "city", "country", "phone"]
        ),
        "shippers.csv": _csv(shippers, ["id", "company_name", "phone"]),
        "customers.csv": _csv(
            customers, ["id", "company_name", "contact_name", "city", "country", "phone"]
        ),
        "products.csv": _csv(
            products,
            [
                "id",
                "product_name",
                "category_id",
                "supplier_id",
                "unit_price",
                "units_in_stock",
                "discontinued",
            ],
        ),
        "orders.csv": _csv(
            orders, ["id", "customer_id", "employee_id", "ordered_on", "shipper_id", "freight"]
        ),
        "order_details.csv": _csv(
            order_details,
            ["order_id", "product_id", "unit_price", "quantity", "discount"],
        ),
    }


def build_specs() -> list[TableSpec]:
    def column(name: str, type_: ColumnType, nullable: bool = False) -> ColumnSpec:
        return ColumnSpec(name=name, source_name=name, type=type_, nullable=nullable)

    return [
        TableSpec(
            name="region",
            source_filename="region.csv",
            primary_key="id",
            columns=(
                column("id", ColumnType.integer),
                column("region_description", ColumnType.text),
            ),
        ),
        TableSpec(
            name="territories",
            source_filename="territories.csv",
            primary_key="id",
            columns=(
                column("id", ColumnType.integer),
                column("territory_description", ColumnType.text),
                column("region_id", ColumnType.integer),
            ),
            foreign_keys=(ForeignKeySpec("region_id", "region", "id"),),
        ),
        TableSpec(
            name="employees",
            source_filename="employees.csv",
            primary_key="id",
            columns=(
                column("id", ColumnType.integer),
                column("first_name", ColumnType.text),
                column("last_name", ColumnType.text),
                column("title", ColumnType.text),
                column("city", ColumnType.text),
                column("country", ColumnType.text),
                column("reports_to", ColumnType.integer, nullable=True),
            ),
            foreign_keys=(ForeignKeySpec("reports_to", "employees", "id"),),
        ),
        TableSpec(
            name="employee_territories",
            source_filename="employee_territories.csv",
            columns=(
                column("employee_id", ColumnType.integer),
                column("territory_id", ColumnType.integer),
            ),
            foreign_keys=(
                ForeignKeySpec("employee_id", "employees", "id"),
                ForeignKeySpec("territory_id", "territories", "id"),
            ),
        ),
        TableSpec(
            name="categories",
            source_filename="categories.csv",
            primary_key="id",
            columns=(
                column("id", ColumnType.integer),
                column("category_name", ColumnType.text),
                column("description", ColumnType.text),
            ),
        ),
        TableSpec(
            name="suppliers",
            source_filename="suppliers.csv",
            primary_key="id",
            columns=(
                column("id", ColumnType.integer),
                column("company_name", ColumnType.text),
                column("contact_name", ColumnType.text),
                column("city", ColumnType.text),
                column("country", ColumnType.text),
                column("phone", ColumnType.text),
            ),
        ),
        TableSpec(
            name="shippers",
            source_filename="shippers.csv",
            primary_key="id",
            columns=(
                column("id", ColumnType.integer),
                column("company_name", ColumnType.text),
                column("phone", ColumnType.text),
            ),
        ),
        TableSpec(
            name="customers",
            source_filename="customers.csv",
            primary_key="id",
            columns=(
                column("id", ColumnType.integer),
                column("company_name", ColumnType.text),
                column("contact_name", ColumnType.text),
                column("city", ColumnType.text),
                column("country", ColumnType.text),
                column("phone", ColumnType.text),
            ),
        ),
        TableSpec(
            name="products",
            source_filename="products.csv",
            primary_key="id",
            columns=(
                column("id", ColumnType.integer),
                column("product_name", ColumnType.text),
                column("category_id", ColumnType.integer),
                column("supplier_id", ColumnType.integer),
                column("unit_price", ColumnType.numeric),
                column("units_in_stock", ColumnType.integer),
                column("discontinued", ColumnType.boolean),
            ),
            foreign_keys=(
                ForeignKeySpec("category_id", "categories", "id"),
                ForeignKeySpec("supplier_id", "suppliers", "id"),
            ),
        ),
        TableSpec(
            name="orders",
            source_filename="orders.csv",
            primary_key="id",
            columns=(
                column("id", ColumnType.integer),
                column("customer_id", ColumnType.integer),
                column("employee_id", ColumnType.integer),
                column("ordered_on", ColumnType.date),
                column("shipper_id", ColumnType.integer),
                column("freight", ColumnType.numeric),
            ),
            foreign_keys=(
                ForeignKeySpec("customer_id", "customers", "id"),
                ForeignKeySpec("employee_id", "employees", "id"),
                ForeignKeySpec("shipper_id", "shippers", "id"),
            ),
        ),
        TableSpec(
            name="order_details",
            source_filename="order_details.csv",
            columns=(
                column("order_id", ColumnType.integer),
                column("product_id", ColumnType.integer),
                column("unit_price", ColumnType.numeric),
                column("quantity", ColumnType.integer),
                column("discount", ColumnType.numeric),
            ),
            foreign_keys=(
                ForeignKeySpec("order_id", "orders", "id"),
                ForeignKeySpec("product_id", "products", "id"),
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
            print(f"Created account {email}")

        existing = await session.scalar(
            select(Project).where(
                Project.user_id == user.id, Project.name == PROJECT_NAME
            )
        )
        if existing is not None:
            await delete_project(session, existing)
            print("Removed the previous Northwind project")

        project = Project(
            user_id=user.id,
            name=PROJECT_NAME,
            source_type=SourceType.upload,
            is_demo=False,
        )
        session.add(project)
        await session.flush()

        committed = await commit_upload(session, project, build_specs(), build_files())
        await session.commit()

    await engine.dispose()

    print(f"Seeded {PROJECT_NAME} into {project.schema_name}:")
    for table in committed:
        print(f"  {table.name}: {table.row_count} rows")
    print(f"Sign in as {email} and open the {PROJECT_NAME} project.")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default=DEMO_EMAIL)
    parser.add_argument("--password", default=DEMO_PASSWORD)
    args = parser.parse_args()
    await seed(args.email, args.password)


if __name__ == "__main__":
    asyncio.run(main())
