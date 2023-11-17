"""

Revision ID: 0433_sh_add_not_null_check
Revises: 0432_s_add_not_null_check
Create Date: 2023-11-15 22:27:23.511256

"""
from alembic import op
from sqlalchemy import column

revision = "0433_sh_add_not_null_check"
down_revision = "0432_s_add_not_null_check"


def upgrade():
    # acquires access exclusive, but only very briefly as the not_valid stops it doing a full table scan
    op.create_check_constraint(
        "ck_services_history_email_sender_local_part_not_null_check",
        "services_history",
        column("email_sender_local_part").is_not(None),
        postgresql_not_valid=True,
    )


def downgrade():
    op.drop_constraint("ck_services_history_email_sender_local_part_not_null_check", "services_history")
