"""

Revision ID: 0302_add_org_id_to_services
Revises: 0301_upload_letters_permission
Create Date: 2019-08-06 09:43:57.993510

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0302_add_org_id_to_services'
down_revision = '0301_upload_letters_permission'


def upgrade():
    op.add_column('services', sa.Column('organisation_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f('ix_services_organisation_id'), 'services', ['organisation_id'], unique=False)
    op.create_foreign_key("fk_service_organisation", 'services', 'organisation', ['organisation_id'], ['id'])
    op.add_column('services_history', sa.Column('organisation_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f('ix_services_history_organisation_id'), 'services_history', ['organisation_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_services_history_organisation_id'), table_name='services_history')
    op.drop_column('services_history', 'organisation_id')
    op.drop_constraint("fk_service_organisation", 'services', type_='foreignkey')
    op.drop_index(op.f('ix_services_organisation_id'), table_name='services')
    op.drop_column('services', 'organisation_id')
