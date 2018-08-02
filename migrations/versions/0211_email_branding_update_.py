"""

Revision ID: 0211_email_branding_update
Revises: 0210_remove_monthly_billing
Create Date: 2018-07-31 18:00:20.457755

"""
from alembic import op
import sqlalchemy as sa


revision = '0211_email_branding_update'
down_revision = '0210_remove_monthly_billing'


def upgrade():
    op.add_column('email_branding', sa.Column('text', sa.String(length=255), nullable=True))
    op.execute('UPDATE email_branding SET text = name')


def downgrade():
    op.drop_column('email_branding', 'text')
