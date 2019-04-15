"""

Revision ID: 0287_add_go_live_user
Revises: 0286_add_unique_email_name
Create Date: 2019-04-15 16:50:22.275673

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0287_add_go_live_user'
down_revision = '0286_add_unique_email_name'


def upgrade():
    op.add_column('services', sa.Column('go_live_at', sa.DateTime(), nullable=True))
    op.add_column('services', sa.Column('go_live_user_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_services_go_live_user', 'services', 'users', ['go_live_user_id'], ['id'])
    op.add_column('services_history', sa.Column('go_live_at', sa.DateTime(), nullable=True))
    op.add_column('services_history', sa.Column('go_live_user_id', postgresql.UUID(as_uuid=True), nullable=True))


def downgrade():
    op.drop_column('services_history', 'go_live_user_id')
    op.drop_column('services_history', 'go_live_at')
    op.drop_constraint('fk_services_go_live_user', 'services', type_='foreignkey')
    op.drop_column('services', 'go_live_user_id')
    op.drop_column('services', 'go_live_at')
