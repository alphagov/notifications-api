"""
Create Date: 2024-06-01 16:35:30.12345
"""

from alembic import op


revision = "0454_th_has_unsub_link_validate"
down_revision = "0453_th_has_unsub_link_constrain"


def upgrade():
    # These only acquire a SHARE UPDATE EXCLUSIVE lock.
    op.execute(
        "ALTER TABLE templates_history VALIDATE CONSTRAINT ck_templates_history_has_unsubscribe_link_not_null_check"
    )


def downgrade():
    # non-reversible
    pass
