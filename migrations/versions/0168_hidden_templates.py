"""

Revision ID: 0168_hidden_templates
Revises: 0167_add_precomp_letter_svc_perm
Create Date: 2018-02-21 14:05:04.448977

"""
from alembic import op
import sqlalchemy as sa


revision = '0168_hidden_templates'
down_revision = '0167_add_precomp_letter_svc_perm'


def upgrade():
    op.add_column('templates', sa.Column('hidden', sa.Boolean(), nullable=True))
    op.add_column('templates_history', sa.Column('hidden', sa.Boolean(), nullable=True))

    op.execute('UPDATE templates SET hidden=false')
    op.execute('UPDATE templates_history SET hidden=false')

    op.alter_column('templates', 'hidden', nullable=False)
    op.alter_column('templates_history', 'hidden', nullable=False)


def downgrade():
    op.drop_column('templates_history', 'hidden')
    op.drop_column('templates', 'hidden')
