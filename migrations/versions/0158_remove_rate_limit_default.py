"""

Revision ID: 0158_remove_rate_limit_default
Revises: 0157_add_rate_limit_to_service
Create Date: 2018-01-09 14:33:08.313893

"""
from alembic import op
import sqlalchemy as sa


revision = '0158_remove_rate_limit_default'
down_revision = '0157_add_rate_limit_to_service'


def upgrade():
    op.execute("ALTER TABLE services ALTER rate_limit DROP DEFAULT")
    op.execute("ALTER TABLE services_history ALTER rate_limit DROP DEFAULT")

def downgrade():
    op.execute("ALTER TABLE services ALTER rate_limit SET DEFAULT '3000'")
    op.execute("ALTER TABLE services_history ALTER rate_limit SET DEFAULT '3000'")
