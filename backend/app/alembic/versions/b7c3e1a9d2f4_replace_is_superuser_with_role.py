"""Replace is_superuser with role

Existing superusers become admins; everyone else becomes a member.
No user is migrated to manager.

Revision ID: b7c3e1a9d2f4
Revises: fe56fa70289e
Create Date: 2026-11-13 23:30:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b7c3e1a9d2f4"
down_revision = "fe56fa70289e"
branch_labels = None
depends_on = None


def upgrade():
    # A constant server default lets PostgreSQL add the column without a table
    # rewrite; every existing row starts as "member".
    op.add_column(
        "user",
        sa.Column(
            "role", sa.String(length=20), nullable=False, server_default="member"
        ),
    )
    op.execute("UPDATE \"user\" SET role = 'admin' WHERE is_superuser IS TRUE")
    op.create_check_constraint(
        "ck_user_role", "user", "role IN ('admin', 'manager', 'member')"
    )
    op.drop_column("user", "is_superuser")


def downgrade():
    # Managers become regular users: a downgrade can only remove access.
    op.add_column(
        "user",
        sa.Column(
            "is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.execute("UPDATE \"user\" SET is_superuser = TRUE WHERE role = 'admin'")
    op.alter_column("user", "is_superuser", server_default=None)
    op.drop_constraint("ck_user_role", "user", type_="check")
    op.drop_column("user", "role")
