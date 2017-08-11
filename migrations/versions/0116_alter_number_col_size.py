"""empty message

Revision ID: 0116_alter_number_col_size
Revises: 0115_add_inbound_numbers
Create Date: 2017-08-11 17:48:30.358584

"""

# revision identifiers, used by Alembic.
revision = '0116_alter_number_col_size'
down_revision = '0115_add_inbound_numbers'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.alter_column('inbound_numbers', 'number',
               existing_type=sa.VARCHAR(length=11),
               type_=sa.String(length=12),
               existing_nullable=False)


def downgrade():
    op.alter_column('inbound_numbers', 'number',
               existing_type=sa.String(length=12),
               type_=sa.VARCHAR(length=11),
               existing_nullable=False)
