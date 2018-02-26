"""

Revision ID: 0169_hidden_templates_nullable
Revises: 0168_hidden_templates
Create Date: 2018-02-21 14:05:04.448977

"""
from alembic import op


revision = '0169_hidden_templates_nullable'
down_revision = '0168_hidden_templates'


def upgrade():
    op.alter_column('templates', 'hidden', nullable=True)
    op.alter_column('templates_history', 'hidden', nullable=True)


def downgrade():
    op.alter_column('templates', 'hidden', nullable=False)
    op.alter_column('templates_history', 'hidden', nullable=False)
