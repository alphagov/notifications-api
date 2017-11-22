"""

Revision ID: 0144_template_service_letter
Revises: 0143_remove_reply_to
Create Date: 2017-11-17 15:42:16.401229

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0144_template_service_letter'
down_revision = '0143_remove_reply_to'


def upgrade():
    op.add_column('templates',
                  sa.Column('service_letter_contact_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('templates_service_letter_contact_id_fkey', 'templates',
                          'service_letter_contacts', ['service_letter_contact_id'], ['id'])

    op.add_column('templates_history',
                  sa.Column('service_letter_contact_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('templates_history_service_letter_contact_id_fkey', 'templates_history',
                          'service_letter_contacts', ['service_letter_contact_id'], ['id'])


def downgrade():
    op.drop_constraint('templates_service_letter_contact_id_fkey', 'templates', type_='foreignkey')
    op.drop_column('templates', 'service_letter_contact_id')

    op.drop_constraint('templates_history_service_letter_contact_id_fkey', 'templates_history', type_='foreignkey')
    op.drop_column('templates_history', 'service_letter_contact_id')
