"""
Create Date: 2024-07-02 08:51:23.266628
"""

from alembic import op
from sqlalchemy import DateTime


revision = "0463_backfill_created_at"
down_revision = "0462_unsubscribe_created_at"


DAY_ZERO = "2024-05-29"  # The day before we added the table


def upgrade():
    op.execute(f"""
        UPDATE
            unsubscribe_request_report
        SET
            created_at = '{DAY_ZERO}'
        WHERE
            created_at is NULL
    """)
    op.alter_column(
        "unsubscribe_request_report",
        "created_at",
        existing_type=DateTime(),
        nullable=False,
    )


def downgrade():
    op.alter_column(
        "unsubscribe_request_report",
        "created_at",
        existing_type=DateTime(),
        nullable=True,
    )
    op.execute(f"""
        UPDATE
            unsubscribe_request_report
        SET
            created_at = NULL
        WHERE
            created_at <= '{DAY_ZERO}'
    """)
