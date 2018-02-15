"""empty message

Revision ID: 0118_service_sms_senders
Revises: 0117_international_sms_notify
Create Date: 2017-09-05 17:29:38.921045

"""

# revision identifiers, used by Alembic.
revision = '0118_service_sms_senders'
down_revision = '0117_international_sms_notify'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():
    op.create_table('service_sms_senders',
                    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('sms_sender', sa.String(length=11), nullable=False),
                    sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('is_default', sa.Boolean(), nullable=False),
                    sa.Column('inbound_number_id', postgresql.UUID(as_uuid=True), nullable=True),
                    sa.Column('created_at', sa.DateTime(), nullable=False),
                    sa.Column('updated_at', sa.DateTime(), nullable=True),
                    sa.ForeignKeyConstraint(['inbound_number_id'], ['inbound_numbers.id'], ),
                    sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_service_sms_senders_inbound_number_id'), 'service_sms_senders', ['inbound_number_id'],
                    unique=True)
    op.create_index(op.f('ix_service_sms_senders_service_id'), 'service_sms_senders', ['service_id'], unique=True)

    # populate govuk seeded service
    op.execute("""
        INSERT INTO service_sms_senders
        (id, sms_sender, service_id, is_default, inbound_number_id, created_at, updated_at)
        VALUES ('286d6176-adbe-7ea7-ba26-b7606ee5e2a4', 'GOVUK', 'd6aa2c68-a2d9-4437-ab19-3ae8eb202553', true, null, now(), null)
    """)


def downgrade():
    op.drop_index(op.f('ix_service_sms_senders_service_id'), table_name='service_sms_senders')
    op.drop_index(op.f('ix_service_sms_senders_inbound_number_id'), table_name='service_sms_senders')
    op.drop_table('service_sms_senders')
