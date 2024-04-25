"""

Revision ID: 0414_org_user_permissions
Revises: 0413_ft_billing_letter_despatch
Create Date: 2023-06-09 13:27:00.294865

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0414_org_user_permissions"
down_revision = "0413_ft_billing_letter_despatch"


def upgrade():
    op.create_table(
        "organisation_user_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "permission", sa.Enum("can_make_services_live", name="organisation_user_permission_types"), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisation.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organisation_id", "user_id", "permission", name="uix_organisation_user_permission"),
    )
    op.create_index(
        op.f("ix_organisation_user_permissions_organisation_id"),
        "organisation_user_permissions",
        ["organisation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organisation_user_permissions_permission"),
        "organisation_user_permissions",
        ["permission"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organisation_user_permissions_user_id"), "organisation_user_permissions", ["user_id"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_organisation_user_permissions_user_id"), table_name="organisation_user_permissions")
    op.drop_index(op.f("ix_organisation_user_permissions_permission"), table_name="organisation_user_permissions")
    op.drop_index(op.f("ix_organisation_user_permissions_organisation_id"), table_name="organisation_user_permissions")
    op.drop_table("organisation_user_permissions")
    op.execute("drop type organisation_user_permission_types")
