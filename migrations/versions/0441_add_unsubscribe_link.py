"""

Revision ID: 0441_add_unsubscribe_link
Revises: 0440_new_sms_allowance_n_rate
Create Date: 2024-03-25 14:38:54.618674

"""

from alembic import op
import sqlalchemy as sa


revision = "0441_add_unsubscribe_link"
down_revision = "0440_new_sms_allowance_n_rate"


def upgrade():
    op.add_column("notifications", sa.Column("unsubscribe_link", sa.String(), nullable=True))
    op.create_check_constraint(
        "ck_unsubscribe_link_is_null_if_notification_not_an_email",
        "notifications",
        """
        notification_type = 'email' OR unsubscribe_link is null
        """,
    )


def downgrade():
    op.drop_column("notifications", "unsubscribe_link")
