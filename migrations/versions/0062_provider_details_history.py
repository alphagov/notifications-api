"""empty message

Revision ID: 0062_provider_details_history
Revises: 0061_add_client_reference
Create Date: 2016-12-14 13:00:24.226990

"""

# revision identifiers, used by Alembic.
revision = '0062_provider_details_history'
down_revision = '0061_add_client_reference'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.get_bind()
    op.execute('UPDATE provider_details SET active = false WHERE active is null')

    op.alter_column('provider_details', 'active', existing_type=sa.BOOLEAN(), nullable=False)

    op.create_table('provider_details_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('display_name', sa.String(), nullable=False),
        sa.Column('identifier', sa.String(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('notification_type', postgresql.ENUM('email', 'sms', 'letter', name='notification_type', create_type=False), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('provider_details_history')

    op.alter_column('provider_details_history', 'active', existing_type=sa.BOOLEAN(), nullable=True)
    op.alter_column('provider_details', 'active', existing_type=sa.BOOLEAN(), nullable=True)
