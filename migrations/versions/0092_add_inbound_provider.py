"""empty message

Revision ID: 0092_add_inbound_provider
Revises: 0091_letter_billing
Create Date: 2017-06-02 16:07:35.445423

"""

# revision identifiers, used by Alembic.
revision = '0092_add_inbound_provider'
down_revision = '0091_letter_billing'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.add_column('inbound_sms', sa.Column('provider', sa.String(), nullable=True))


def downgrade():
    op.drop_column('inbound_sms', 'provider')
