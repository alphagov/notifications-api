"""
* add version and updated_at to provider_details
* set active to not nullable (any existing null is set to false)
* create provider_details_history table, mimicking provider_details

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
    op.add_column('provider_details', sa.Column('updated_at', sa.DateTime()))

    op.execute('UPDATE provider_details SET active = false WHERE active is null')
    op.alter_column('provider_details', 'active', nullable=False)

    op.add_column('provider_details', sa.Column('version', sa.Integer(), nullable=True))
    op.execute('UPDATE provider_details SET version = 1')
    op.alter_column('provider_details', 'version', nullable=False)

    op.create_table('provider_details_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('display_name', sa.String(), nullable=False),
        sa.Column('identifier', sa.String(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('notification_type', postgresql.ENUM('email', 'sms', 'letter', name='notification_type', create_type=False), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', 'version')
    )
    op.execute(
        'INSERT INTO provider_details_history' +
        ' (id, display_name, identifier, priority, notification_type, active, version)' +
        ' SELECT id, display_name, identifier, priority, notification_type, active, version FROM provider_details'
    )


def downgrade():
    op.drop_table('provider_details_history')

    op.alter_column('provider_details', 'active', existing_type=sa.BOOLEAN(), nullable=True)
    op.drop_column('provider_details', 'version')
    op.drop_column('provider_details', 'updated_at')
