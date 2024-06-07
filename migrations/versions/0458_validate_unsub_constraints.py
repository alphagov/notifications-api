"""
Create Date: 2024-06-07 10:37:51.851999
"""

from alembic import op

revision = "0458_validate_unsub_constraints"
down_revision = "0457_th_unsub_constraint"


def upgrade():
    # These only acquire a SHARE UPDATE EXCLUSIVE lock.
    op.execute("ALTER TABLE templates VALIDATE CONSTRAINT ck_templates_non_email_has_unsubscribe_false")
    op.execute("ALTER TABLE templates_history VALIDATE CONSTRAINT ck_templates_history_non_email_has_unsubscribe_false")


def downgrade():
    pass
