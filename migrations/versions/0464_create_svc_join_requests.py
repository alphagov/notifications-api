from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0464_create_svc_join_requests"
down_revision = "0463_backfill_created_at"

values = ["pending", "approved", "rejected"]
request_status_enum = sa.Enum(*values, name="request_status")


def upgrade():
    request_status_enum.create(op.get_bind())
    op.create_table(
        "service_join_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("uuid_generate_v4()")),
        sa.Column("requester_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("services.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "status",
            postgresql.ENUM(
                *values,
                name="request_status",
                create_type=False,
                checkfirst=True,
                inherit_schema=True,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("status_changed_at", sa.DateTime(), nullable=True),
        sa.Column("status_changed_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
    )

    op.create_table(
        "contacted_users",
        sa.Column(
            "service_join_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("service_join_requests.id"),
            primary_key=True,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
    )


def downgrade():
    # Drop the contacted_users table first due to foreign key dependency
    op.drop_table("contacted_users")

    op.drop_table("service_join_requests")

    request_status_enum.drop(op.get_bind(), checkfirst=False)
