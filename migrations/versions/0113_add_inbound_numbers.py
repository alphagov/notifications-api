"""empty message

Revision ID: 0113_add_inbound_numbers
Revises: 0112_add_start_end_dates
Create Date: 2017-08-03 11:08:00.970476

"""

# revision identifiers, used by Alembic.
revision = '0113_add_inbound_numbers'
down_revision = '0112_add_start_end_dates'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.create_table('inbound_numbers',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('number', sa.String(length=11), nullable=False),
    sa.Column('provider', sa.String(), nullable=False),
    sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('number')
    )
    op.create_index(op.f('ix_inbound_numbers_service_id'), 'inbound_numbers', ['service_id'], unique=True)


def downgrade():
    op.drop_index(op.f('ix_inbound_numbers_service_id'), table_name='inbound_numbers')
    op.drop_table('inbound_numbers')
