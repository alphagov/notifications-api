"""
Create Date: 2024-06-01 16:35:30.12345
"""

from alembic import op
import sqlalchemy as sa


revision = "0455_th_has_unsub_link_not_null"
down_revision = "0454_th_has_unsub_link_validate"


def upgrade():
    # quoth the docs:

    # SET NOT NULL may only be applied to a column provided none of the records in the table contain a NULL value
    # for the column. Ordinarily this is checked during the ALTER TABLE by scanning the entire table; however, if a
    # valid CHECK constraint is found which proves no NULL can exist, then the table scan is skipped.

    # so now we can add regular nullable constraints without worrying about a lengthy table scan.
    op.alter_column("templates_history", "has_unsubscribe_link", nullable=False)

    # now get rid of the old constraint now that it's no longer needed. this is a weird process overall
    op.drop_constraint("ck_templates_history_has_unsubscribe_link_not_null_check", "templates_history")


def downgrade():
    op.alter_column("templates_history", "has_unsubscribe_link", nullable=True)

    # notably this creates _with_ validating constraint otherwise we'll end up with inconsistency
    op.create_check_constraint(
        "ck_templates_history_has_unsubscribe_link_not_null_check",
        "templates_history",
        sa.column("has_unsubscribe_link").is_not(None),
    )
