"""

Revision ID: 0290_org_go_live_notes
Revises: 0289_precompiled_for_all
Create Date: 2019-05-13 14:55:10.291781

"""
from alembic import op
import sqlalchemy as sa


revision = '0290_org_go_live_notes'
down_revision = '0289_precompiled_for_all'


def upgrade():
    op.add_column('organisation', sa.Column('request_to_go_live_notes', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('organisation', 'request_to_go_live_notes')
