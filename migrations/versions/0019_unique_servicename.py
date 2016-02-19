"""empty message

Revision ID: 0019_unique_servicename
Revises: 0018_unique_emailfrom
Create Date: 2016-02-18 11:45:29.102891

"""

# revision identifiers, used by Alembic.
revision = '0019_unique_servicename'
down_revision = '0018_unique_emailfrom'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_unique_constraint(None, 'services', ['name'])


def downgrade():
    op.drop_constraint(None, 'services', type_='unique')
