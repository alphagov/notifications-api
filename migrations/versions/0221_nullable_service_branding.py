"""
 Revision ID: 0221_nullable_service_branding
Revises: 0220_email_brand_type_non_null
Create Date: 2018-08-24 13:36:49.346156
 """
from alembic import op


revision = '0221_nullable_service_branding'
down_revision = '0220_email_brand_type_non_null'


def upgrade():

    op.drop_constraint('services_branding_fkey', 'services', type_='foreignkey')

    op.drop_index('ix_services_history_branding', table_name='services_history')
    op.drop_index('ix_services_branding', table_name='services')

    op.alter_column('services_history', 'branding', nullable=True)
    op.alter_column('services', 'branding', nullable=True)


def downgrade():

    op.create_index(op.f('ix_services_branding'), 'services', ['branding'], unique=False)
    op.create_index(op.f('ix_services_history_branding'), 'services_history', ['branding'], unique=False)

    op.create_foreign_key(None, 'services', 'branding_type', ['branding'], ['name'])

    op.alter_column('services', 'branding', nullable=False)
    op.alter_column('services_history', 'branding', nullable=False)
