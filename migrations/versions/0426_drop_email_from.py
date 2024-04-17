"""

Revision ID: 0426_drop_email_from
Revises: 0425_unique_service_name_2
Create Date: 2023-09-29 18:47:48.703294

"""

from alembic import op
import sqlalchemy as sa


revision = "0426_drop_email_from"
down_revision = "0425_unique_service_name_2"


def upgrade():
    # these commands both acquire `access exclusive` locks.

    op.drop_column("services", "email_from")
    op.drop_column("services_history", "email_from")


def downgrade():
    op.add_column("services_history", sa.Column("email_from", sa.TEXT(), nullable=True))
    op.add_column("services", sa.Column("email_from", sa.TEXT(), nullable=True))
