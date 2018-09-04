"""
Revision ID: 0223_add_domain_constraint
Revises: 0222_drop_service_branding
Create Date: 2018-08-24 13:36:49.346156
 """
from alembic import op


revision = '0223_add_domain_constraint'
down_revision = '0222_drop_service_branding'


def upgrade():

    op.execute("""
        update
            email_branding
        set
            domain = null
        where
            domain = ''
    """)
    op.create_unique_constraint('uq_email_branding_domain', 'email_branding', ['domain'])


def downgrade():

    op.drop_constraint('uq_email_branding_domain', 'email_branding')
