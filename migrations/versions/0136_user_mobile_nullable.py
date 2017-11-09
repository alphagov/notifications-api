"""

Revision ID: 0136_user_mobile_nullable
Revises: 0135_stats_template_usage
Create Date: 2017-11-08 11:49:05.773974

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import column
from sqlalchemy.dialects import postgresql

revision = '0136_user_mobile_nullable'
down_revision = '0135_stats_template_usage'


def upgrade():
    op.alter_column('users', 'mobile_number', nullable=True)

    op.create_check_constraint(
        'ck_users_mobile_or_email_auth',
        'users',
        "auth_type = 'email_auth' or mobile_number is not null"
    )

def downgrade():
    op.alter_column('users', 'mobile_number', nullable=False)
    op.drop_constraint('ck_users_mobile_or_email_auth', 'users')
