from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0461_svc_join_req"
down_revision = "0460_letter_rates_july_2024"

request_status_enum = sa.Enum("PENDING", "APPROVED", "REJECTED", name="requeststatus")


def upgrade():
    op.create_table(
        "service_join_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("uuid_generate_v4()")),
        sa.Column("requester_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("services.id"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("status", request_status_enum, nullable=False, server_default="PENDING"),
        sa.Column("status_changed_at", sa.DateTime, nullable=True),
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
