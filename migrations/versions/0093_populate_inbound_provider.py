"""empty message

Revision ID: 0093_populate_inbound_provider
Revises: 0092_add_inbound_provider
Create Date: 2017-05-22 10:23:43.939050

"""

# revision identifiers, used by Alembic.
revision = '0093_populate_inbound_provider'
down_revision = '0092_add_inbound_provider'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.execute("UPDATE inbound_sms SET provider='mmg' WHERE provider is null")


def downgrade():
    op.execute("UPDATE inbound_sms SET provider=null WHERE provider = 'mmg'")
