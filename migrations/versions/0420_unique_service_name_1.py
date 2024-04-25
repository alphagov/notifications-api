"""

Revision ID: 0420_unique_service_name_1
Revises: 0419_take_part_in_research
Create Date: 2023-08-24 16:26:03.488048

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0420_unique_service_name_1"
down_revision = "0419_take_part_in_research"


def upgrade():
    op.add_column("services", sa.Column("normalised_service_name", sa.String(), nullable=True, unique=True))
    op.add_column("services_history", sa.Column("normalised_service_name", sa.String(), nullable=True))


def downgrade():
    op.drop_column("services", "normalised_service_name")
    op.drop_column("services_history", "normalised_service_name")
