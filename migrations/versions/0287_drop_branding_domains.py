"""

Revision ID: 0287_drop_branding_domains
Revises: 0286_add_unique_email_name
Create Date: 2019-04-05 16:25:11.535816

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0287_drop_branding_domains'
down_revision = '0286_add_unique_email_name'


def upgrade():
    op.drop_constraint('uq_email_branding_domain', 'email_branding', type_='unique')
    op.drop_column('email_branding', 'domain')
    op.drop_constraint('letter_branding_domain_key', 'letter_branding', type_='unique')
    op.drop_column('letter_branding', 'domain')


def downgrade():
    op.add_column('letter_branding', sa.Column('domain', sa.TEXT(), autoincrement=False, nullable=True))
    op.create_unique_constraint('letter_branding_domain_key', 'letter_branding', ['domain'])
    op.add_column('email_branding', sa.Column('domain', sa.TEXT(), autoincrement=False, nullable=True))
    op.create_unique_constraint('uq_email_branding_domain', 'email_branding', ['domain'])
