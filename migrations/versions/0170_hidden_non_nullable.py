"""

Revision ID: 0170_hidden_non_nullable
Revises: 0169_hidden_templates_nullable
Create Date: 2018-02-21 14:05:04.448977

"""
from alembic import op


revision = '0170_hidden_non_nullable'
down_revision = '0169_hidden_templates_nullable'


def upgrade():
    op.execute('UPDATE templates SET hidden=false WHERE hidden is NULL')
    op.execute('UPDATE templates_history SET hidden=false WHERE hidden is NULL')

    op.alter_column('templates', 'hidden', nullable=False)
    op.alter_column('templates_history', 'hidden', nullable=False)


def downgrade():
    op.alter_column('templates', 'hidden', nullable=True)
    op.alter_column('templates_history', 'hidden', nullable=True)
