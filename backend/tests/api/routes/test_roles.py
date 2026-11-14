import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.core.permissions import Role
from app.models import ItemCreate, User, UserCreate
from tests.utils.item import create_random_item
from tests.utils.user import user_authentication_headers
from tests.utils.utils import random_email, random_lower_string

API = settings.API_V1_STR


def create_user_with_role(db: Session, role: Role) -> tuple[User, str]:
    password = random_lower_string()
    user = crud.create_user(
        session=db,
        user_create=UserCreate(email=random_email(), password=password, role=role),
    )
    return user, password


def login(client: TestClient, user: User, password: str) -> dict[str, str]:
    return user_authentication_headers(
        client=client, email=user.email, password=password
    )


@pytest.fixture(scope="module")
def role_headers(client: TestClient, db: Session) -> dict[Role, dict[str, str]]:
    headers = {}
    for role in Role:
        user, password = create_user_with_role(db, role)
        headers[role] = login(client, user, password)
    return headers


EXPECTED = {Role.ADMIN: True, Role.MANAGER: True, Role.MEMBER: False}
ADMIN_ONLY = {Role.ADMIN: True, Role.MANAGER: False, Role.MEMBER: False}


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize(
    ("method", "path", "allowed", "body"),
    [
        ("GET", "/users/", EXPECTED, None),
        ("GET", "/users/{other}", EXPECTED, None),
        ("GET", "/metrics/", EXPECTED, None),
        ("POST", "/users/", ADMIN_ONLY, "new_user"),
        ("PATCH", "/users/{other}", ADMIN_ONLY, {"full_name": "Changed"}),
        ("PATCH", "/users/{other}", ADMIN_ONLY, {"role": "manager"}),
        ("PATCH", "/users/{other}", ADMIN_ONLY, {"is_active": False}),
        ("DELETE", "/users/{other}", ADMIN_ONLY, None),
        ("GET", "/items/{other_item}", ADMIN_ONLY, None),
        ("PUT", "/items/{other_item}", ADMIN_ONLY, {"title": "Changed"}),
        ("DELETE", "/items/{other_item}", ADMIN_ONLY, None),
    ],
)
def test_role_matrix(
    client: TestClient,
    db: Session,
    role_headers: dict[Role, dict[str, str]],
    role: Role,
    method: str,
    path: str,
    allowed: dict[Role, bool],
    body: object,
) -> None:
    other, _ = create_user_with_role(db, Role.MEMBER)
    other_item = create_random_item(db)
    url = API + path.format(other=other.id, other_item=other_item.id)
    if body == "new_user":
        body = {"email": random_email(), "password": random_lower_string()}

    r = client.request(method, url, headers=role_headers[role], json=body)

    if allowed[role]:
        assert r.status_code == 200, r.text
    else:
        assert r.status_code == 403, r.text


@pytest.mark.parametrize("role", [Role.MANAGER, Role.MEMBER])
def test_item_list_is_limited_to_own_items(
    client: TestClient, db: Session, role: Role
) -> None:
    user, password = create_user_with_role(db, role)
    owned = crud.create_item(
        session=db, item_in=ItemCreate(title="mine"), owner_id=user.id
    )
    foreign = create_random_item(db)
    headers = login(client, user, password)

    r = client.get(f"{API}/items/", headers=headers)
    assert r.status_code == 200
    assert r.json()["count"] == 1
    assert [item["id"] for item in r.json()["data"]] == [str(owned.id)]

    assert client.get(f"{API}/items/{owned.id}", headers=headers).status_code == 200
    r = client.get(f"{API}/items/{foreign.id}", headers=headers)
    assert r.status_code == 403


def test_me_returns_role_permissions(
    client: TestClient, role_headers: dict[Role, dict[str, str]]
) -> None:
    r = client.get(f"{API}/users/me", headers=role_headers[Role.MANAGER])
    assert r.json()["role"] == "manager"
    assert r.json()["permissions"] == ["metrics:read", "users:read"]


# --- Privilege escalation -------------------------------------------------


def test_member_cannot_change_own_role_via_me(client: TestClient, db: Session) -> None:
    user, password = create_user_with_role(db, Role.MEMBER)
    headers = login(client, user, password)
    r = client.patch(
        f"{API}/users/me",
        headers=headers,
        json={"full_name": "Still Member", "role": "admin", "is_active": True},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "member"
    db.refresh(user)
    assert user.role == Role.MEMBER


def test_signup_ignores_requested_role(client: TestClient) -> None:
    r = client.post(
        f"{API}/users/signup",
        json={
            "email": random_email(),
            "password": random_lower_string(),
            "role": "admin",
        },
    )
    assert r.status_code == 200
    assert r.json()["role"] == "member"


def test_invalid_role_is_rejected(
    client: TestClient, db: Session, role_headers: dict[Role, dict[str, str]]
) -> None:
    other, _ = create_user_with_role(db, Role.MEMBER)
    r = client.patch(
        f"{API}/users/{other.id}",
        headers=role_headers[Role.ADMIN],
        json={"role": "owner"},
    )
    assert r.status_code == 422


def test_null_role_is_rejected_and_role_unchanged(
    client: TestClient, db: Session, role_headers: dict[Role, dict[str, str]]
) -> None:
    other, _ = create_user_with_role(db, Role.MANAGER)
    r = client.patch(
        f"{API}/users/{other.id}",
        headers=role_headers[Role.ADMIN],
        json={"role": None},
    )
    assert r.status_code == 422
    db.refresh(other)
    assert other.role == Role.MANAGER

    # Omitting the field still works and keeps the role.
    r = client.patch(
        f"{API}/users/{other.id}",
        headers=role_headers[Role.ADMIN],
        json={"full_name": "No Role Change"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "manager"


@pytest.mark.parametrize("body", [{"role": "manager"}, {"is_active": False}])
def test_admin_cannot_demote_or_deactivate_self(
    client: TestClient, db: Session, body: dict[str, object]
) -> None:
    admin, password = create_user_with_role(db, Role.ADMIN)
    r = client.patch(
        f"{API}/users/{admin.id}", headers=login(client, admin, password), json=body
    )
    assert r.status_code == 400
    db.refresh(admin)
    assert admin.role == Role.ADMIN and admin.is_active


def test_admin_can_edit_own_name_via_admin_endpoint(
    client: TestClient, db: Session
) -> None:
    admin, password = create_user_with_role(db, Role.ADMIN)
    r = client.patch(
        f"{API}/users/{admin.id}",
        headers=login(client, admin, password),
        json={"full_name": "Renamed", "role": "admin", "is_active": True},
    )
    assert r.status_code == 200
    assert r.json()["full_name"] == "Renamed"


# --- Existing sessions ----------------------------------------------------


def test_role_change_applies_to_existing_session(
    client: TestClient, db: Session, role_headers: dict[Role, dict[str, str]]
) -> None:
    user, password = create_user_with_role(db, Role.MEMBER)
    headers = login(client, user, password)
    assert client.get(f"{API}/users/", headers=headers).status_code == 403

    admin = role_headers[Role.ADMIN]
    r = client.patch(f"{API}/users/{user.id}", headers=admin, json={"role": "manager"})
    assert r.status_code == 200
    assert client.get(f"{API}/users/", headers=headers).status_code == 200

    r = client.patch(f"{API}/users/{user.id}", headers=admin, json={"role": "member"})
    assert r.status_code == 200
    assert client.get(f"{API}/users/", headers=headers).status_code == 403


def test_admin_demoted_to_manager_loses_write_access_in_same_session(
    client: TestClient, db: Session
) -> None:
    admin, password = create_user_with_role(db, Role.ADMIN)
    other_admin, other_password = create_user_with_role(db, Role.ADMIN)
    target, _ = create_user_with_role(db, Role.MEMBER)
    headers = login(client, admin, password)  # token issued while still admin

    r = client.patch(
        f"{API}/users/{admin.id}",
        headers=login(client, other_admin, other_password),
        json={"role": "manager"},
    )
    assert r.status_code == 200

    assert client.get(f"{API}/users/", headers=headers).status_code == 200
    assert client.get(f"{API}/users/{target.id}", headers=headers).status_code == 200
    new_user = {"email": random_email(), "password": random_lower_string()}
    assert (
        client.post(f"{API}/users/", headers=headers, json=new_user).status_code == 403
    )
    for body in ({"role": "admin"}, {"is_active": False}):
        r = client.patch(f"{API}/users/{target.id}", headers=headers, json=body)
        assert r.status_code == 403
    r = client.patch(f"{API}/users/{admin.id}", headers=headers, json={"role": "admin"})
    assert r.status_code == 403
    assert client.delete(f"{API}/users/{target.id}", headers=headers).status_code == 403

    db.refresh(target)
    db.refresh(admin)
    assert target.role == Role.MEMBER and target.is_active
    assert admin.role == Role.MANAGER


def test_deactivation_ends_existing_session(
    client: TestClient, db: Session, role_headers: dict[Role, dict[str, str]]
) -> None:
    user, password = create_user_with_role(db, Role.MANAGER)
    headers = login(client, user, password)
    assert client.get(f"{API}/users/me", headers=headers).status_code == 200

    r = client.patch(
        f"{API}/users/{user.id}",
        headers=role_headers[Role.ADMIN],
        json={"is_active": False},
    )
    assert r.status_code == 200
    r = client.get(f"{API}/users/me", headers=headers)
    assert r.status_code == 401
    assert r.json()["detail"] == "Inactive user"


def test_deleted_user_session_is_rejected(
    client: TestClient, db: Session, role_headers: dict[Role, dict[str, str]]
) -> None:
    user, password = create_user_with_role(db, Role.MEMBER)
    headers = login(client, user, password)
    r = client.delete(f"{API}/users/{user.id}", headers=role_headers[Role.ADMIN])
    assert r.status_code == 200
    assert client.get(f"{API}/users/me", headers=headers).status_code == 401


def test_invalid_token_is_unauthorized(client: TestClient) -> None:
    r = client.get(f"{API}/users/me", headers={"Authorization": "Bearer invalid"})
    assert r.status_code == 401
