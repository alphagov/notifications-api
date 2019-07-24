import os

"""

Revision ID: 0300_migrate_org_types
Revises: 0299_org_types_table
Create Date: 2019-07-24 16:18:27.467361

"""
from alembic import op
import sqlalchemy as sa


revision = '0300_migrate_org_types'
down_revision = '0299_org_types_table'

environment = os.environ['NOTIFY_ENVIRONMENT']


def upgrade():
    if environment != "production":
        op.execute("""
            UPDATE
                organisation
            SET
                organisation_type = 'nhs_local'
            WHERE
                organisation.organisation_type = 'nhs'
        """)

        op.execute("""
            UPDATE
                services
            SET
                organisation_type = 'nhs_local'
            WHERE
                services.organisation_type = 'nhs'
        """)

    op.alter_column('organisation_types', 'name', existing_type=sa.VARCHAR(), type_=sa.String(length=255))

    op.create_foreign_key(
        'organisation_organisation_type_fkey', 'organisation', 'organisation_types', ['organisation_type'], ['name']
    )

    op.create_foreign_key(
        'services_organisation_type_fkey', 'services', 'organisation_types', ['organisation_type'], ['name']
    )


def downgrade():
    op.drop_constraint('services_organisation_type_fkey', 'services', type_='foreignkey')

    op.drop_constraint('organisation_organisation_type_fkey', 'organisation', type_='foreignkey')

    op.alter_column('organisation_types', 'name', existing_type=sa.String(length=255), type_=sa.VARCHAR())

    if environment != "production":
        op.execute("""
            UPDATE
                organisation
            SET
                organisation_type = 'nhs'
            WHERE
                organisation_type = 'nhs_local'
        """)

        op.execute("""
            UPDATE
                services
            SET
                organisation_type = 'nhs'
            WHERE
                organisation_type = 'nhs_local'
        """)
