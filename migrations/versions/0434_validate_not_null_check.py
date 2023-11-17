"""

Revision ID: 0434_validate_not_null_check
Revises: 0433_sh_add_not_null_check
Create Date: 2023-11-15 22:27:23.511256

"""
from alembic import op

revision = "0434_validate_not_null_check"
down_revision = "0433_sh_add_not_null_check"


def upgrade():
    # These only acquire a SHARE UPDATE EXCLUSIVE lock.
    op.execute("ALTER TABLE services VALIDATE CONSTRAINT ck_services_email_sender_local_part_not_null_check")
    op.execute(
        "ALTER TABLE services_history VALIDATE CONSTRAINT ck_services_history_email_sender_local_part_not_null_check"
    )


def downgrade():
    pass
