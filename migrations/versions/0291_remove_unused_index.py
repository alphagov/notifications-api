"""

Revision ID: 0291_remove_unused_index
Revises: 0290_org_go_live_notes
Create Date: 2019-05-16 14:05:18.104274

"""
from alembic import op
import sqlalchemy as sa


revision = '0291_remove_unused_index'
down_revision = '0290_org_go_live_notes'


def upgrade():
    op.drop_index('ix_domain_domain', table_name='domain')


def downgrade():
    op.create_index('ix_domain_domain', 'domain', ['domain'], unique=True)
