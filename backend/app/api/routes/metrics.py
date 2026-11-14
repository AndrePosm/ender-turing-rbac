from fastapi import APIRouter, Depends
from sqlmodel import SQLModel, col, func, select

from app.api.deps import SessionDep, require_permission
from app.core.permissions import Permission
from app.models import Item, User

router = APIRouter(prefix="/metrics", tags=["metrics"])


class MetricsPublic(SQLModel):
    total_users: int
    active_users: int
    users_by_role: dict[str, int]
    total_items: int


@router.get(
    "/",
    dependencies=[Depends(require_permission(Permission.METRICS_READ))],
    response_model=MetricsPublic,
)
def read_metrics(session: SessionDep) -> MetricsPublic:
    """
    Basic usage metrics (stub).
    """
    by_role = session.exec(select(User.role, func.count()).group_by(User.role)).all()
    return MetricsPublic(
        total_users=session.exec(select(func.count()).select_from(User)).one(),
        active_users=session.exec(
            select(func.count()).select_from(User).where(col(User.is_active))
        ).one(),
        users_by_role={str(role): count for role, count in by_role},
        total_items=session.exec(select(func.count()).select_from(Item)).one(),
    )
