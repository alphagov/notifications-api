"""

Revision ID: 0435_s_swap_check_for_not_null
Revises: 0434_validate_not_null_check
Create Date: 2023-11-15 22:27:23.511256

"""
from alembic import op
from sqlalchemy import column

revision = "0435_s_swap_check_for_not_null"
down_revision = "0434_validate_not_null_check"


def upgrade():
    # quoth the docs:

    # SET NOT NULL may only be applied to a column provided none of the records in the table contain a NULL value
    # for the column. Ordinarily this is checked during the ALTER TABLE by scanning the entire table; however, if a
    # valid CHECK constraint is found which proves no NULL can exist, then the table scan is skipped.

    # so now we can add regular nullable constraints without worrying about a lengthy table scan.
    op.alter_column("services", "email_sender_local_part", nullable=False)

    # now get rid of the old constraint now that it's no longer needed. this is a weird process overall
    op.drop_constraint("ck_services_email_sender_local_part_not_null_check", "services")


def downgrade():
    op.alter_column("services", "email_sender_local_part", nullable=True)

    # notably this creates _with_ validating constraint otherwise we'll end up with inconsistency
    op.create_check_constraint(
        "ck_services_email_sender_local_part_not_null_check", "services", column("email_sender_local_part").is_not(None)
    )
