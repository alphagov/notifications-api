"""

Revision ID: 0296_template_redacted_fix
Revises: 0295_api_key_constraint
Create Date: 2019-06-07 17:02:14.350064

"""
from alembic import op


revision = '0296_template_redacted_fix'
down_revision = '0295_api_key_constraint'


def upgrade():
    op.execute("""
        INSERT INTO template_redacted (template_id, redact_personalisation, updated_at, updated_by_id)
        SELECT templates.id, FALSE, now(), templates.created_by_id
        FROM templates
        WHERE templates.id NOT IN (SELECT template_id FROM template_redacted WHERE template_id = templates.id)
        ;
    """)


def downgrade():
    pass
