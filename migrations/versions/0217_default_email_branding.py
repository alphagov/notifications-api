"""
 Revision ID: 0217_default_email_branding
Revises: 0216_remove_colours
Create Date: 2018-08-24 13:36:49.346156
 """
from alembic import op
from app.models import BRANDING_ORG

revision = '0217_default_email_branding'
down_revision = '0216_remove_colours'


def upgrade():
    op.execute("""
        update
            email_branding
        set
            brand_type = '{}'
        where
            brand_type = null
    """.format(BRANDING_ORG))


def downgrade():
    pass
