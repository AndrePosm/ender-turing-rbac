"""Create local demo accounts for the manager and member roles.

Development only. Missing accounts are created with FIRST_SUPERUSER_PASSWORD.
Existing accounts are never modified; a wrong role, an inactive account or a
password that differs from FIRST_SUPERUSER_PASSWORD is reported as a conflict.

Usage (from backend/): uv run python -m app.seed_demo_users
"""

import logging
import sys

from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.core.db import engine
from app.core.permissions import Role
from app.core.security import verify_password
from app.models import User, UserCreate

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DEMO_USERS = [
    ("manager@example.com", Role.MANAGER, "Demo Manager"),
    ("member@example.com", Role.MEMBER, "Demo Member"),
]


def report_existing(user: User, expected_role: Role) -> int:
    """Log whether an existing account matches; never modifies it."""
    problems = []
    if user.role != expected_role:
        problems.append(f"role is {user.role}, expected {expected_role}")
    if not user.is_active:
        problems.append("account is inactive")
    # Read-only check: the possible rehash returned by verify_password is ignored.
    verified, _ = verify_password(
        settings.FIRST_SUPERUSER_PASSWORD, user.hashed_password
    )
    if not verified:
        problems.append("password differs from FIRST_SUPERUSER_PASSWORD")
    if problems:
        logger.warning(f"CONFLICT {user.email}: {'; '.join(problems)}; left unchanged")
        return 1
    logger.info(f"ok       {user.email} ({expected_role}, existing)")
    return 0


def main() -> int:
    if settings.FASTAPI_ENV != "development":
        logger.error("Refusing to run: FASTAPI_ENV is not 'development'.")
        return 1

    conflicts = 0
    with Session(engine) as session:
        admin = crud.get_user_by_email(session=session, email=settings.FIRST_SUPERUSER)
        if admin is None:
            conflicts += 1
            logger.warning(
                f"CONFLICT {settings.FIRST_SUPERUSER}: missing "
                "(run scripts/prestart.sh to create it)"
            )
        else:
            conflicts += report_existing(admin, Role.ADMIN)

        for email, role, full_name in DEMO_USERS:
            user = crud.get_user_by_email(session=session, email=email)
            if user is None:
                crud.create_user(
                    session=session,
                    user_create=UserCreate(
                        email=email,
                        password=settings.FIRST_SUPERUSER_PASSWORD,
                        full_name=full_name,
                        role=role,
                    ),
                )
                logger.info(f"created  {email} ({role})")
            else:
                conflicts += report_existing(user, role)

    if conflicts:
        logger.warning(
            f"{conflicts} conflict(s); fix them in the admin UI or use another DB."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
