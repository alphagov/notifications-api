"""empty message

Revision ID: 0017_emailfrom_notnull
Revises: 0016_add_email_from
Create Date: 2016-02-18 11:41:25.753694

"""

# revision identifiers, used by Alembic.
revision = '0017_emailfrom_notnull'
down_revision = '0016_add_email_from'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.alter_column('services', 'email_from',
                    existing_type=sa.TEXT(),
                    nullable=False)


def downgrade():
    op.alter_column('services', 'email_from',
                    existing_type=sa.TEXT(),
                    nullable=True)
