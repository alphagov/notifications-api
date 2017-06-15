"""empty message

Revision ID: 0098_tfl_dar
Revises: 0097_notnull_inbound_provider
Create Date: 2017-06-05 16:15:17.744908

"""

# revision identifiers, used by Alembic.
revision = '0098_tfl_dar'
down_revision = '0097_notnull_inbound_provider'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

TFL_DAR_ID = '1d70f564-919b-4c68-8bdf-b8520d92516e'


def upgrade():
    op.execute("""INSERT INTO organisation VALUES (
        '{}',
        '',
        'tfl_dar_x2.png',
        ''
    )""".format(TFL_DAR_ID))


def downgrade():
    op.execute("""
        DELETE FROM organisation WHERE "id" = '{}'
    """.format(TFL_DAR_ID))
