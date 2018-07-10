"""

Revision ID: 0202_service_data_retention
Revises: 0201_another_letter_org
Create Date: 2018-07-10 11:22:01.761829

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0202_service_data_retention'
down_revision = '0201_another_letter_org'


def upgrade():
    op.create_table('service_data_retention',
                    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('notification_type',
                              postgresql.ENUM(name='notification_type', create_type=False),
                              nullable=False),
                    sa.Column('days_of_retention', sa.Integer(), nullable=False),
                    sa.Column('created_at', sa.DateTime(), nullable=False),
                    sa.Column('updated_at', sa.DateTime(), nullable=True),
                    sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_service_data_retention_service_id'), 'service_data_retention', ['service_id'],
                    unique=False)


def downgrade():
    op.drop_index(op.f('ix_service_data_retention_service_id'), table_name='service_data_retention')
    op.drop_table('service_data_retention')
