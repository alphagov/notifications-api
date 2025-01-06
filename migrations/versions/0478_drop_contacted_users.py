from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0478_drop_contacted_users"
down_revision = "0477_create_sjr_contacted_users"


def upgrade():
    op.drop_table("contacted_users")


def downgrade():
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

    op.execute(
        """
        INSERT INTO contacted_users (service_join_request_id, user_id)
        SELECT service_join_request_id, user_id FROM service_join_request_contacted_users;
        """
    )
