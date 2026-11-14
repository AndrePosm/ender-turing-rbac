from collections.abc import Generator

import pytest


@pytest.fixture(scope="session")
def db() -> Generator[None]:
    """Override the shared autouse `db` fixture from tests/conftest.py.

    Migration tests use only their own temporary database, so the development
    database must not be initialized or cleaned up for them.
    """
    yield
