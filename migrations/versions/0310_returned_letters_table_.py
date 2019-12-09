"""

Revision ID: 0310_returned_letters_table
Revises: 0309_add_uq_key_row_number
Create Date: 2019-12-09 12:13:49.432993

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0310_returned_letters_table'
down_revision = '0309_add_uq_key_row_number'


def upgrade():
    op.create_table('returned_letters',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('reported_at', sa.DateTime(), nullable=False),
        sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('notification_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('notification_id')
    )
    op.create_index(op.f('ix_returned_letters_service_id'), 'returned_letters', ['service_id'], unique=False)


def downgrade():
    op.drop_table('returned_letters')
