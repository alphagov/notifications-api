"""

Revision ID: 0386_email_branding_alt_text
Revises: 0385_letter_branding_pools
Create Date: 2022-10-21 14:26:12.421574

"""

import sqlalchemy as sa
from alembic import op

revision = "0386_email_branding_alt_text"
down_revision = "0385_letter_branding_pools"


def upgrade():
    op.add_column("email_branding", sa.Column("alt_text", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("email_branding", "alt_text")
