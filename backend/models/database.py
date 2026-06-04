import json

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models.trip import Base
from utils.config import settings


engine = create_async_engine(settings.database_url, echo=False, future=True)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _should_migrate_sqlite_trips(sync_connection) -> bool:
    inspector = inspect(sync_connection)
    if "trips" not in inspector.get_table_names():
        return False

    columns = {column["name"]: column for column in inspector.get_columns("trips")}
    expected_columns = {
        "user_id",
        "origin",
        "destination",
        "travel_start_date",
        "travel_end_date",
        "budget",
        "waypoints",
        "created_at",
    }
    if not expected_columns.issubset(columns.keys()):
        return True

    user_id_column = columns.get("user_id")
    if user_id_column is None:
        return True

    column_type = str(user_id_column.get("type", "")).lower()
    if "int" not in column_type:
        return True

    foreign_keys = inspector.get_foreign_keys("trips")
    return not any(fk.get("referred_table") == "users" and fk.get("constrained_columns") == ["user_id"] for fk in foreign_keys)


def _normalize_legacy_identifier(identifier: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in identifier.strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned or "guest"


def _ensure_legacy_user(sync_connection, identifier: str) -> int:
    from models.trip import User

    normalized = _normalize_legacy_identifier(identifier)
    email = f"{normalized}@local"

    result = sync_connection.execute(
        User.__table__.select().where(
            (User.__table__.c.username == normalized) | (User.__table__.c.email == email)
        )
    )
    row = result.mappings().first()
    if row:
        return int(row["id"])

    insert_result = sync_connection.execute(
        User.__table__.insert().values(
            username=normalized,
            email=email,
            hashed_password="legacy-placeholder",
            full_name=None,
            is_active=True,
        )
    )
    inserted_primary_key = insert_result.inserted_primary_key
    if inserted_primary_key and inserted_primary_key[0] is not None:
        return int(inserted_primary_key[0])

    lookup = sync_connection.execute(User.__table__.select().where(User.__table__.c.email == email))
    created_row = lookup.mappings().first()
    if created_row is None:
        raise RuntimeError(f"Unable to create legacy user for {identifier!r}.")
    return int(created_row["id"])


def _migrate_sqlite_schema(sync_connection) -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    inspector = inspect(sync_connection)
    user_table_columns = {column["name"] for column in inspector.get_columns("users")} if "users" in inspector.get_table_names() else set()
    if "users" not in inspector.get_table_names() or not {"username", "email", "hashed_password", "created_at", "is_active"}.issubset(user_table_columns):
        return

    if "trips" not in inspector.get_table_names():
        return

    if not _should_migrate_sqlite_trips(sync_connection):
        return

    sync_connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        existing_columns = {column["name"] for column in inspector.get_columns("trips")}
        if "travel_start_date" not in existing_columns:
            sync_connection.exec_driver_sql("ALTER TABLE trips ADD COLUMN travel_start_date TEXT")
        if "travel_end_date" not in existing_columns:
            sync_connection.exec_driver_sql("ALTER TABLE trips ADD COLUMN travel_end_date TEXT")
        if "budget" not in existing_columns:
            sync_connection.exec_driver_sql("ALTER TABLE trips ADD COLUMN budget REAL")
    finally:
        sync_connection.exec_driver_sql("PRAGMA foreign_keys=ON")


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_sqlite_schema)
