"""

Revision ID: 0304_remove_org_to_service
Revises: 0303_populate_services_org_id
Create Date: 2019-08-15 14:49:00.754390

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0304_remove_org_to_service'
down_revision = '0303_populate_services_org_id'


def upgrade():
    op.drop_table('organisation_to_service')


def downgrade():
    op.create_table('organisation_to_service',
                    sa.Column('service_id', postgresql.UUID(), autoincrement=False, nullable=False),
                    sa.Column('organisation_id', postgresql.UUID(), autoincrement=False, nullable=False),
                    sa.ForeignKeyConstraint(['organisation_id'], ['organisation.id'],
                                            name='organisation_to_service_organisation_id_fkey'),
                    sa.ForeignKeyConstraint(['service_id'], ['services.id'],
                                            name='organisation_to_service_service_id_fkey'),
                    sa.PrimaryKeyConstraint('service_id', name='organisation_to_service_pkey')
                    )
