"""

Revision ID: 0432_s_add_not_null_check
Revises: 0431_migrate_email_local_part
Create Date: 2023-11-15 22:27:23.511256

"""
from alembic import op
from sqlalchemy import column

revision = "0432_s_add_not_null_check"
down_revision = "0431_migrate_email_local_part"


def upgrade():
    # acquires access exclusive, but only very briefly as the not_valid stops it doing a full table scan
    op.create_check_constraint(
        "ck_services_email_sender_local_part_not_null_check",
        "services",
        column("email_sender_local_part").is_not(None),
        postgresql_not_valid=True,
    )


def downgrade():
    op.drop_constraint("ck_services_email_sender_local_part_not_null_check", "services")
