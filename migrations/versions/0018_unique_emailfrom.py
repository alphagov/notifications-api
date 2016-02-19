"""empty message

Revision ID: 0018_unique_emailfrom
Revises: 0017_emailfrom_notnull
Create Date: 2016-02-18 11:42:18.246280

"""

# revision identifiers, used by Alembic.
revision = '0018_unique_emailfrom'
down_revision = '0017_emailfrom_notnull'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_unique_constraint(None, 'services', ['email_from'])


def downgrade():
    op.drop_constraint(None, 'services', type_='unique')
