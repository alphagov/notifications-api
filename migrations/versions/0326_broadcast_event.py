"""

Revision ID: 0326_broadcast_event
Revises: 0325_int_letter_rates_fix
Create Date: 2020-07-24 12:40:35.809523

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0326_broadcast_event'
down_revision = '0325_int_letter_rates_fix'


def upgrade():
    op.create_table('broadcast_event',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('broadcast_message_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=False),
        sa.Column('message_type', sa.String(), nullable=False),
        sa.Column('transmitted_content', postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True),
        sa.Column('transmitted_areas', postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=False),
        sa.Column('transmitted_sender', sa.String(), nullable=False),
        sa.Column('transmitted_starts_at', sa.DateTime(), nullable=True),
        sa.Column('transmitted_finishes_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['broadcast_message_id'], ['broadcast_message.id'], ),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    # this shouldn't be nullable. it defaults to `[]` in python.
    op.alter_column('broadcast_message', 'areas', existing_type=postgresql.JSONB(astext_type=sa.Text()), nullable=False)
    # this can't be nullable. it defaults to 'draft' in python.
    op.alter_column('broadcast_message', 'status', existing_type=sa.VARCHAR(), nullable=False)
    op.create_foreign_key(None, 'broadcast_message', 'broadcast_status_type', ['status'], ['name'])


def downgrade():
    op.drop_constraint('broadcast_message_status_fkey', 'broadcast_message', type_='foreignkey')
    op.alter_column('broadcast_message', 'status', existing_type=sa.VARCHAR(), nullable=True)
    op.alter_column('broadcast_message', 'areas', existing_type=postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    op.drop_table('broadcast_event')
