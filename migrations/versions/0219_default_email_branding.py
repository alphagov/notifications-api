"""
 Revision ID: 0219_default_email_branding
Revises: 0218_another_letter_org
Create Date: 2018-08-24 13:36:49.346156
 """
from alembic import op
from app.models import BRANDING_ORG

revision = '0219_default_email_branding'
down_revision = '0218_another_letter_org'


def upgrade():
    op.execute("""
        update
            email_branding
        set
            brand_type = '{}'
        where
            brand_type is null
    """.format(BRANDING_ORG))


def downgrade():
    pass
