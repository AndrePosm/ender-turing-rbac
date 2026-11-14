from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    MANAGER = "manager"
    MEMBER = "member"


class Permission(StrEnum):
    USERS_READ = "users:read"
    USERS_WRITE = "users:write"
    METRICS_READ = "metrics:read"
    # Access to items owned by other users; everyone can manage their own items.
    ITEMS_READ_ALL = "items:read_all"
    ITEMS_WRITE_ALL = "items:write_all"


# Single source of truth for access rules. The frontend receives the same
# list through `UserPublic.permissions`.
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    Role.MANAGER: frozenset({Permission.USERS_READ, Permission.METRICS_READ}),
    Role.MEMBER: frozenset(),
}


def permissions_for(role: Role | str) -> list[Permission]:
    return sorted(ROLE_PERMISSIONS.get(Role(role), frozenset()))


def has_permission(role: Role | str, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(Role(role), frozenset())
