"""empty message

Revision ID: 0112_add_start_end_dates
Revises: 0111_drop_old_service_flags
Create Date: 2017-07-12 13:35:45.636618

"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op

from app.dao.date_util import get_month_start_and_end_date_in_utc
from sqlalchemy import text

down_revision = "0111_drop_old_service_flags"
revision = "0112_add_start_end_dates"


def upgrade():
    op.drop_index("uix_monthly_billing", "monthly_billing")
    op.alter_column("monthly_billing", "month", nullable=True)
    op.alter_column("monthly_billing", "year", nullable=True)
    op.add_column("monthly_billing", sa.Column("start_date", sa.DateTime))
    op.add_column("monthly_billing", sa.Column("end_date", sa.DateTime))
    conn = op.get_bind()
    results = conn.execute(text("Select id, month, year from monthly_billing"))
    res = results.fetchall()
    for x in res:
        start_date, end_date = get_month_start_and_end_date_in_utc(
            datetime(int(x.year), datetime.strptime(x.month, "%B").month, 1)
        )
        conn.execute(
            "update monthly_billing set start_date = '{}', end_date = '{}' where id = '{}'".format(
                start_date, end_date, x.id
            )
        )
    op.alter_column("monthly_billing", "start_date", nullable=False)
    op.alter_column("monthly_billing", "end_date", nullable=False)
    op.create_index(
        op.f("uix_monthly_billing"), "monthly_billing", ["service_id", "start_date", "notification_type"], unique=True
    )


def downgrade():
    op.drop_column("monthly_billing", "start_date")
    op.drop_column("monthly_billing", "end_date")

    op.create_index(
        op.f("uix_monthly_billing"),
        "monthly_billing",
        ["service_id", "month", "year", "notification_type"],
        unique=True,
    )
