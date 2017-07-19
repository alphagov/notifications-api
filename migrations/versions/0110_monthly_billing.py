"""empty message

Revision ID: 0110_monthly_billing
Revises: 0109_rem_old_noti_status
Create Date: 2017-07-13 14:35:03.183659

"""

# revision identifiers, used by Alembic.
revision = '0110_monthly_billing'
down_revision = '0109_rem_old_noti_status'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():

    op.create_table('monthly_billing',
                    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('month', sa.String(), nullable=False),
                    sa.Column('year', sa.Float(), nullable=False),
                    sa.Column('notification_type',
                              postgresql.ENUM('email', 'sms', 'letter', name='notification_type', create_type=False),
                              nullable=False),
                    sa.Column('monthly_totals', postgresql.JSON(), nullable=False),
                    sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_monthly_billing_service_id'), 'monthly_billing', ['service_id'], unique=False)
    op.create_index(op.f('uix_monthly_billing'), 'monthly_billing', ['service_id', 'month', 'year', 'notification_type'], unique=True)


def downgrade():
    op.drop_table('monthly_billing')
