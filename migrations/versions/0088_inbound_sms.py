"""empty message

Revision ID: 0088_inbound_sms
Revises: 0087_scheduled_notifications
Create Date: 2017-05-22 11:28:53.471004

"""

# revision identifiers, used by Alembic.
revision = '0088_inbound_sms'
down_revision = '0087_scheduled_notifications'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.create_table(
        'inbound_sms',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('content', sa.String, nullable=False),
        sa.Column('notify_number', sa.String, nullable=False),
        sa.Column('user_number', sa.String, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('provider_date', sa.DateTime, nullable=True),
        sa.Column('provider_reference', sa.String, nullable=True),

        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_inbound_sms_service_id'), 'inbound_sms', ['service_id'], unique=False)
    op.create_index(op.f('ix_inbound_sms_user_number'), 'inbound_sms', ['user_number'], unique=False)


def downgrade():
    op.drop_table('inbound_sms')
