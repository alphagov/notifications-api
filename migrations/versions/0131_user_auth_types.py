"""

Revision ID: 0131_user_auth_types
Revises: 0130_service_email_reply_to_row
Create Date: 2017-10-27 16:19:51.458863

"""
from alembic import op
import sqlalchemy as sa


revision = '0131_user_auth_types'
down_revision = '0130_service_email_reply_to_row'


def upgrade():
    op.create_table(
        'auth_type',
        sa.Column('name', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('name')
    )
    op.execute("INSERT INTO auth_type VALUES ('email_auth'), ('sms_auth')")

    op.add_column('users', sa.Column('auth_type', sa.String(), nullable=False, server_default='sms_auth'))

    op.create_index(op.f('ix_users_auth_type'), 'users', ['auth_type'], unique=False)
    op.create_foreign_key(None, 'users', 'auth_type', ['auth_type'], ['name'])

    op.add_column('invited_users', sa.Column('auth_type', sa.String(), nullable=False, server_default='sms_auth'))

    op.create_index(op.f('ix_invited_users_auth_type'), 'invited_users', ['auth_type'], unique=False)
    op.create_foreign_key(None, 'invited_users', 'auth_type', ['auth_type'], ['name'])


def downgrade():
    op.drop_column('users', 'auth_type')
    op.drop_column('invited_users', 'auth_type')
    op.drop_table('auth_type')
