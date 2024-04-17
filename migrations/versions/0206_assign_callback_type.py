"""

Revision ID: 0206_assign_callback_type
Revises: 0205_service_callback_type
Create Date: 2018-07-18 10:43:43.864835

"""

import sqlalchemy as sa
from alembic import op

revision = "0206_assign_callback_type"
down_revision = "0205_service_callback_type"


def upgrade():
    op.execute("update service_callback_api set callback_type = 'delivery_status' where callback_type is null")


def downgrade():
    pass
