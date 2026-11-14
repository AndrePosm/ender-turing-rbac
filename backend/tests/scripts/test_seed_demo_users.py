import logging

import pytest
from sqlmodel import Session

from app import crud, seed_demo_users
from app.core.config import settings
from app.core.permissions import Role
from app.core.security import verify_password
from app.models import User, UserCreate, UserUpdate
from tests.utils.utils import random_email, random_lower_string

# Every test uses random emails (removed by the shared fixture's cleanup), so
# the real admin and demo accounts are never read or modified.


def create_user(
    db: Session,
    email: str,
    role: Role,
    password: str | None = None,
    is_active: bool = True,
) -> User:
    return crud.create_user(
        session=db,
        user_create=UserCreate(
            email=email,
            password=password or settings.FIRST_SUPERUSER_PASSWORD,
            role=role,
            is_active=is_active,
        ),
    )


@pytest.fixture
def demo(monkeypatch: pytest.MonkeyPatch, db: Session) -> dict[str, str]:
    """Point the command at a disposable admin and disposable demo emails."""
    emails = {
        "admin": random_email(),
        "manager": random_email(),
        "member": random_email(),
    }
    create_user(db, emails["admin"], Role.ADMIN)
    monkeypatch.setattr(settings, "FIRST_SUPERUSER", emails["admin"])
    monkeypatch.setattr(
        seed_demo_users,
        "DEMO_USERS",
        [
            (emails["manager"], Role.MANAGER, "Demo Manager"),
            (emails["member"], Role.MEMBER, "Demo Member"),
        ],
    )
    return emails


def get(db: Session, email: str) -> User | None:
    db.expire_all()
    return crud.get_user_by_email(session=db, email=email)


def test_refuses_outside_development(
    monkeypatch: pytest.MonkeyPatch, db: Session, demo: dict[str, str]
) -> None:
    monkeypatch.setattr(settings, "FASTAPI_ENV", None)
    assert seed_demo_users.main() == 1
    assert get(db, demo["manager"]) is None
    assert get(db, demo["member"]) is None


def test_creates_missing_accounts(db: Session, demo: dict[str, str]) -> None:
    assert seed_demo_users.main() == 0

    for key, role in [("manager", Role.MANAGER), ("member", Role.MEMBER)]:
        user = get(db, demo[key])
        assert user is not None
        assert user.role == role
        assert user.is_active
        verified, _ = verify_password(
            settings.FIRST_SUPERUSER_PASSWORD, user.hashed_password
        )
        assert verified


def test_preserves_existing_accounts(db: Session, demo: dict[str, str]) -> None:
    assert seed_demo_users.main() == 0
    manager = get(db, demo["manager"])
    assert manager is not None
    before = (manager.id, manager.hashed_password, manager.role, manager.full_name)

    assert seed_demo_users.main() == 0

    manager = get(db, demo["manager"])
    assert manager is not None
    assert (
        manager.id,
        manager.hashed_password,
        manager.role,
        manager.full_name,
    ) == before


@pytest.mark.parametrize(
    ("role", "is_active", "own_password", "expected"),
    [
        (Role.ADMIN, True, False, "role is admin, expected member"),
        (Role.MEMBER, False, False, "account is inactive"),
        (Role.MEMBER, True, True, "password differs from FIRST_SUPERUSER_PASSWORD"),
    ],
)
def test_reports_conflicts_without_changes(
    db: Session,
    demo: dict[str, str],
    caplog: pytest.LogCaptureFixture,
    role: Role,
    is_active: bool,
    own_password: bool,
    expected: str,
) -> None:
    existing = create_user(
        db,
        demo["member"],
        role,
        password=random_lower_string() if own_password else None,
        is_active=is_active,
    )
    before = (existing.hashed_password, existing.role, existing.is_active)

    with caplog.at_level(logging.INFO, logger=seed_demo_users.logger.name):
        assert seed_demo_users.main() == 1

    assert f"CONFLICT {demo['member']}: {expected}" in caplog.text
    member = get(db, demo["member"])
    assert member is not None
    assert (member.hashed_password, member.role, member.is_active) == before
    # Non-conflicting accounts are still handled.
    assert get(db, demo["manager"]) is not None


def test_reports_missing_or_changed_admin(
    db: Session,
    demo: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    admin = get(db, demo["admin"])
    assert admin is not None
    crud.update_user(
        session=db,
        db_user=admin,
        user_in=UserUpdate(password=random_lower_string()),
    )
    with caplog.at_level(logging.INFO, logger=seed_demo_users.logger.name):
        assert seed_demo_users.main() == 1
    assert f"CONFLICT {demo['admin']}: password differs" in caplog.text

    caplog.clear()
    monkeypatch.setattr(settings, "FIRST_SUPERUSER", random_email())
    with caplog.at_level(logging.INFO, logger=seed_demo_users.logger.name):
        assert seed_demo_users.main() == 1
    assert "missing" in caplog.text
