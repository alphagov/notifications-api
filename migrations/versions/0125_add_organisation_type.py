"""

Revision ID: 0125_add_organisation_type
Revises: 0124_add_free_sms_fragment_limit
Create Date: 2017-10-05 14:03:00.248005

"""

import sqlalchemy as sa
from alembic import op

revision = "0125_add_organisation_type"
down_revision = "0124_add_free_sms_fragment_limit"


def upgrade():
    op.add_column("services", sa.Column("organisation_type", sa.String(length=255), nullable=True))
    op.add_column("services_history", sa.Column("organisation_type", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("services", "organisation_type")
    op.drop_column("services_history", "organisation_type")
