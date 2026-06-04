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

    if not _should_migrate_sqlite_trips(sync_connection):
        return

    inspector = inspect(sync_connection)
    if "trips" not in inspector.get_table_names():
        return

    sync_connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        rows = sync_connection.exec_driver_sql(
            "SELECT id, user_id, origin, destination, waypoints, created_at FROM trips ORDER BY id"
        ).mappings().all()

        if not rows:
            sync_connection.exec_driver_sql("DROP TABLE trips")
            sync_connection.exec_driver_sql(
                """
                CREATE TABLE trips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    origin TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    waypoints JSON NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            sync_connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_trips_user_id ON trips(user_id)")
            return

        sync_connection.exec_driver_sql("DROP TABLE IF EXISTS trips_migrated")
        sync_connection.exec_driver_sql(
            """
            CREATE TABLE trips_migrated (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                waypoints JSON NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )

        legacy_user_ids: dict[str, int] = {}
        for row in rows:
            legacy_identifier = str(row["user_id"] or "guest").strip() or "guest"
            if legacy_identifier not in legacy_user_ids:
                legacy_user_ids[legacy_identifier] = _ensure_legacy_user(sync_connection, legacy_identifier)

            waypoints = row["waypoints"]
            if isinstance(waypoints, str):
                try:
                    waypoints = json.loads(waypoints)
                except json.JSONDecodeError:
                    waypoints = [waypoints]
            elif waypoints is None:
                waypoints = []

            sync_connection.exec_driver_sql(
                """
                INSERT INTO trips_migrated (id, user_id, origin, destination, waypoints, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    legacy_user_ids[legacy_identifier],
                    row["origin"],
                    row["destination"],
                    json.dumps(waypoints),
                    row["created_at"],
                ),
            )

        sync_connection.exec_driver_sql("DROP TABLE trips")
        sync_connection.exec_driver_sql("ALTER TABLE trips_migrated RENAME TO trips")
        sync_connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_trips_user_id ON trips(user_id)")
    finally:
        sync_connection.exec_driver_sql("PRAGMA foreign_keys=ON")


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_sqlite_schema)
