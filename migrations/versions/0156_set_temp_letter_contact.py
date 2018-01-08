"""

Revision ID: 0156_set_temp_letter_contact
Revises: 0155_revert_0153
Create Date: 2018-01-05 17:04:20.596271

"""
from alembic import op


revision = '0156_set_temp_letter_contact'
down_revision = '0155_revert_0153'


def upgrade():
    query = """
        UPDATE templates t SET service_letter_contact_id = (
            SELECT id from service_letter_contacts
            WHERE service_id = t.service_id
            and is_default = true
        )
        WHERE template_type = 'letter'
    """
    op.execute(query)
    history_query = """
        UPDATE templates_history t_history set service_letter_contact_id = (
            SELECT service_letter_contact_id from templates
            where service_letter_contact_id is not null 
            and id = t_history.id
            and version = t_history.version
        )
    """
    op.execute(history_query)


def downgrade():
    op.execute("UPDATE templates set service_letter_contact_id = null")
    op.execute("UPDATE templates_history set service_letter_contact_id = null")
