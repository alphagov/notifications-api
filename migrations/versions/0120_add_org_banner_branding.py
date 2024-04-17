"""

Revision ID: 0120_add_org_banner_branding
Revises: 0119_add_email_reply_to
Create Date: 2017-09-18 14:18:49.087143

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0120_add_org_banner_branding"
down_revision = "0119_add_email_reply_to"


def upgrade():
    op.execute("INSERT INTO branding_type VALUES ('org_banner')")


def downgrade():
    op.execute("UPDATE services SET branding = 'org' WHERE branding = 'org_banner'")
    op.execute("DELETE FROM branding_type WHERE name = 'org_banner'")
