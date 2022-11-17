"""

Revision ID: 0383_webauthn_cred_logged_in_at
Revises: 0382_nhs_letter_branding_id
Create Date: 2022-10-21 14:26:12.421574

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0383_webauthn_cred_logged_in_at'
down_revision = '0382_nhs_letter_branding_id'


def upgrade():
    op.add_column("webauthn_credential", sa.Column("logged_in_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("webauthn_credential", "logged_in_at")
