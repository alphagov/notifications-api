"""empty message

Revision ID: 0075_create_rates_table
Revises: 0074_update_sms_rate
Create Date: 2017-04-24 15:12:18.907629

"""

# revision identifiers, used by Alembic.
import uuid

revision = '0075_create_rates_table'
down_revision = '0074_update_sms_rate'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    notification_types = postgresql.ENUM('email', 'sms', 'letter', name='notification_type', create_type=False)
    op.create_table('rates',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('valid_from', sa.DateTime(), nullable=False),
    sa.Column('rate', sa.Numeric(), nullable=False),
    sa.Column('notification_type', notification_types, nullable=False),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_index(op.f('ix_rates_notification_type'), 'rates', ['notification_type'], unique=False)

    op.get_bind()
    op.execute("INSERT INTO rates(id, valid_from, rate, notification_type) "
               "VALUES('{}', '2016-05-18 00:00:00', 1.65, 'sms')".format(uuid.uuid4()))
    op.execute("INSERT INTO rates(id, valid_from, rate, notification_type) "
               "VALUES('{}', '2017-04-01 00:00:00', 1.58, 'sms')".format(uuid.uuid4()))


def downgrade():
    op.drop_index(op.f('ix_rates_notification_type'), table_name='rates')
    op.drop_table('rates')
