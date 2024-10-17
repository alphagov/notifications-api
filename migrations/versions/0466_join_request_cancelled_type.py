"""
Create Date: 2024-10-15 12:25:32.071832
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0466_join_request_cancelled_type"
down_revision = "0465_rename_svc_join_enum"


def upgrade():
    op.execute("ALTER TYPE service_join_requests_status_type ADD VALUE 'cancelled'")


def downgrade():
    enum_name = "service_join_requests_status_type"
    tmp_name = "tmp_" + enum_name

    new_options = (
        "pending",
        "approved",
        "rejected",
    )
    new_type = sa.Enum(*new_options, name=enum_name)

    op.execute("UPDATE service_join_requests SET status = 'pending' WHERE status = 'cancelled';")

    op.execute(f"ALTER TYPE {enum_name} RENAME TO {tmp_name}")
    new_type.create(op.get_bind())
    # there's a default value, we need to remove this before we can alter the type as it needs to refer to the new
    # column. if this table was in active use we'd need to be very careful about this to minimise access exclusive locks
    # and avoid deadlocks etc
    op.execute(f"ALTER TABLE service_join_requests ALTER COLUMN status DROP DEFAULT")
    op.execute(
        f"ALTER TABLE service_join_requests ALTER COLUMN status TYPE {enum_name} USING status::text::{enum_name}"
    )

    # now re-add the default using the new type
    op.execute(
        f"ALTER TABLE service_join_requests ALTER COLUMN status SET DEFAULT 'pending'::service_join_requests_status_type"
    )
    op.execute(f"DROP TYPE {tmp_name}")
