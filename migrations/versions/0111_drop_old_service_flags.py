"""empty message

Revision ID: 0111_drop_old_service_flags
Revises: 0110_monthly_billing
Create Date: 2017-07-12 13:35:45.636618

"""

# revision identifiers, used by Alembic.
revision = '0111_drop_old_service_flags'
down_revision = '0110_monthly_billing'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.drop_column('services', 'can_send_letters')
    op.drop_column('services', 'can_send_international_sms')
    op.drop_column('services_history', 'can_send_letters')
    op.drop_column('services_history', 'can_send_international_sms')


def downgrade():
    op.add_column('services_history', sa.Column('can_send_international_sms', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False))
    op.add_column('services_history', sa.Column('can_send_letters', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False))
    op.add_column('services', sa.Column('can_send_international_sms', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False))
    op.add_column('services', sa.Column('can_send_letters', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False))
