"""
Create Date: 2024-10-01 11:08:46.900469
"""

revision = "0469_validate_template_ck"
down_revision = "0468_remove_broadcast_type"

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():

    op.execute("ALTER TABLE templates VALIDATE CONSTRAINT chk_templates_letter_languages")
    op.execute("ALTER TABLE templates_history VALIDATE CONSTRAINT chk_templates_history_letter_languages")

    op.execute("ALTER TABLE templates VALIDATE CONSTRAINT ck_templates_letter_attachments")
    op.execute("ALTER TABLE templates_history VALIDATE CONSTRAINT ck_templates_history_letter_attachments")

    op.execute("ALTER TABLE templates VALIDATE CONSTRAINT ck_templates_non_email_has_unsubscribe_false")
    op.execute("ALTER TABLE templates_history VALIDATE CONSTRAINT ck_templates_history_non_email_has_unsubscribe_false")


def downgrade():
    pass
