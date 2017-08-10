"""empty message

Revision ID: 0114_add_inbound_numbers
Revises: 0113_job_created_by_nullable
Create Date: 2017-08-10 17:30:01.507694

"""

# revision identifiers, used by Alembic.
revision = '0114_add_inbound_numbers'
down_revision = '0113_job_created_by_nullable'

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
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('number')
    )
    op.create_index(op.f('ix_inbound_numbers_service_id'), 'inbound_numbers', ['service_id'], unique=True)


def downgrade():
    op.drop_index(op.f('ix_inbound_numbers_service_id'), table_name='inbound_numbers')
    op.drop_table('inbound_numbers')
