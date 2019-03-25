"""empty message

Revision ID: 0284_0283_retry
Revises: 0283_platform_admin_not_live
Create Date: 2016-10-25 17:37:27.660723

"""

# revision identifiers, used by Alembic.
revision = '0284_0283_retry'
down_revision = '0283_platform_admin_not_live'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.execute("""
        UPDATE
            services
        SET
            count_as_live = not users.platform_admin
        FROM
            users, services_history
        WHERE
            services_history.id = services.id and
            services_history.version = 1 and
            services_history.created_by_id = users.id
        ;
    """)

def downgrade():
    op.execute("""
        UPDATE
            services
        SET
            count_as_live = true
        ;
    """)
