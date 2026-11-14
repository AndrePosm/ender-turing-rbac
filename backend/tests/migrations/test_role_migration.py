"""Run the role migration against a throwaway database with pre-migration data.

Alembic's env.py reads `config.attributes["database_url"]`, and
tests/migrations/conftest.py overrides the shared `db` fixture, so these tests
do not touch the development database. The server's maintenance database
("postgres") is used only to create and drop the temporary database.
"""

import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import URL, Engine, create_engine, make_url, text
from sqlalchemy.exc import IntegrityError

from app.core.config import settings

BACKEND_DIR = Path(__file__).resolve().parents[2]
BEFORE = "fe56fa70289e"
ROLE_MIGRATION = "b7c3e1a9d2f4"


@pytest.fixture
def temp_db_url() -> Generator[URL]:
    base = make_url(str(settings.DATABASE_URL))
    name = f"migration_test_{uuid.uuid4().hex[:12]}"
    server = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with server.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield base.set(database=name)
    finally:
        with server.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        server.dispose()


@pytest.fixture
def temp_engine(temp_db_url: URL) -> Generator[Engine]:
    engine = create_engine(temp_db_url)
    yield engine
    engine.dispose()


def alembic_config(url: URL) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "app" / "alembic"))
    config.attributes["database_url"] = url.render_as_string(hide_password=False)
    config.attributes["configure_logger"] = False
    return config


def test_role_migration_on_populated_database(
    temp_db_url: URL, temp_engine: Engine
) -> None:
    config = alembic_config(temp_db_url)
    command.upgrade(config, BEFORE)

    users = {
        "active-admin@example.com": (True, True),
        "inactive-admin@example.com": (True, False),
        "active-user@example.com": (False, True),
        "inactive-user@example.com": (False, False),
    }
    with temp_engine.begin() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == BEFORE
        for email, (is_superuser, is_active) in users.items():
            user_id = uuid.uuid4()
            conn.execute(
                text(
                    'INSERT INTO "user" (id, email, is_superuser, is_active, '
                    "hashed_password, full_name) VALUES "
                    "(:id, :email, :su, :active, :hash, :name)"
                ),
                {
                    "id": user_id,
                    "email": email,
                    "su": is_superuser,
                    "active": is_active,
                    "hash": f"hash-{email}",
                    "name": email.split("@")[0],
                },
            )
            conn.execute(
                text("INSERT INTO item (id, title, owner_id) VALUES (:id, 't', :o)"),
                {"id": uuid.uuid4(), "o": user_id},
            )

    command.upgrade(config, ROLE_MIGRATION)

    with temp_engine.begin() as conn:
        rows = conn.execute(
            text('SELECT email, role, is_active, hashed_password FROM "user"')
        ).all()
        assert {r.email: (r.role, r.is_active) for r in rows} == {
            "active-admin@example.com": ("admin", True),
            "inactive-admin@example.com": ("admin", False),
            "active-user@example.com": ("member", True),
            "inactive-user@example.com": ("member", False),
        }
        assert all(r.hashed_password == f"hash-{r.email}" for r in rows)
        assert conn.scalar(text("SELECT count(*) FROM item")) == 4
        columns = conn.scalars(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'user'"
            )
        ).all()
        assert "is_superuser" not in columns

        # Database default and allowed values.
        conn.execute(
            text(
                'INSERT INTO "user" (id, email, is_active, hashed_password) '
                "VALUES (:id, 'new@example.com', true, 'x')"
            ),
            {"id": uuid.uuid4()},
        )
        assert (
            conn.scalar(text("SELECT role FROM \"user\" WHERE email='new@example.com'"))
            == "member"
        )
        conn.execute(
            text(
                "UPDATE \"user\" SET role = 'manager' "
                "WHERE email = 'active-user@example.com'"
            )
        )

    with pytest.raises(IntegrityError), temp_engine.begin() as conn:
        conn.execute(text("UPDATE \"user\" SET role = 'owner'"))
    with pytest.raises(IntegrityError), temp_engine.begin() as conn:
        conn.execute(text('UPDATE "user" SET role = NULL'))

    # Downgrade only grants superuser to admins; managers lose access.
    command.downgrade(config, BEFORE)
    with temp_engine.begin() as conn:
        rows = conn.execute(text('SELECT email, is_superuser FROM "user"')).all()
        assert {r.email for r in rows if r.is_superuser} == {
            "active-admin@example.com",
            "inactive-admin@example.com",
        }
