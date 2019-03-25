"""empty message

Revision ID: 0282_add_count_as_live
Revises: 0281_non_null_folder_permissions
Create Date: 2016-10-25 17:37:27.660723

"""

# revision identifiers, used by Alembic.
revision = '0282_add_count_as_live'
down_revision = '0281_non_null_folder_permissions'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('services', sa.Column('count_as_live', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('services_history', sa.Column('count_as_live', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    op.drop_column('services_history', 'count_as_live')
    op.drop_column('services', 'count_as_live')
