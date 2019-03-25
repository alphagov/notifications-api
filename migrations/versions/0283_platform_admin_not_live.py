"""empty message

Revision ID: 0283_platform_admin_not_live
Revises: 0282_add_count_as_live
Create Date: 2016-10-25 17:37:27.660723

"""

# revision identifiers, used by Alembic.
revision = '0283_platform_admin_not_live'
down_revision = '0282_add_count_as_live'

from alembic import op
import sqlalchemy as sa


STATEMENT = """
    UPDATE
        services
    SET
        count_as_live = {count_as_live}
    FROM
        users
    WHERE
        services.created_by_id = users.id and
        users.platform_admin is true
    ;
"""


def upgrade():
    op.execute(STATEMENT.format(count_as_live='false'))

def downgrade():
    op.execute(STATEMENT.format(count_as_live='true'))
