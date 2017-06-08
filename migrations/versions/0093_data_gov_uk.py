"""empty message

Revision ID: 0093_data_gov_uk
Revises: 0092_add_inbound_provider
Create Date: 2017-06-05 16:15:17.744908

"""

# revision identifiers, used by Alembic.
revision = '0093_data_gov_uk'
down_revision = '0092_add_inbound_provider'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

DATA_GOV_UK_ID = '123496d4-44cb-4324-8e0a-4187101f4bdc'


def upgrade():
    op.execute("""INSERT INTO organisation VALUES (
        '{}',
        '',
        'data_gov_uk_x2.png',
        ''
    )""".format(DATA_GOV_UK_ID))


def downgrade():
    op.execute("""
        DELETE FROM organisation WHERE "id" = '{}'
    """.format(DATA_GOV_UK_ID))
