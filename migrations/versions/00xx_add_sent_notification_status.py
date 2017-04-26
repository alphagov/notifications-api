"""empty message

Revision ID: 00xx_add_sent_notification_status
Revises: 0075_create_rates_table
Create Date: 2017-04-24 16:55:20.731069

"""

# revision identifiers, used by Alembic.
revision = '00xx_sent_notification_status'
down_revision = '0075_create_rates_table'

from alembic import op
import sqlalchemy as sa

enum_name = 'notify_status_type'
tmp_name = 'tmp_' + enum_name

old_options = (
    'created',
    'sending',
    'delivered',
    'pending',
    'failed',
    'technical-failure',
    'temporary-failure',
    'permanent-failure'
)
new_options = old_options + ('sent',)

old_type = sa.Enum(*old_options, name=enum_name)
new_type = sa.Enum(*new_options, name=enum_name)

alter_str = 'ALTER TABLE {table} ALTER COLUMN status TYPE {enum} USING status::text::notify_status_type '

def upgrade():
    op.execute('ALTER TYPE {enum} RENAME TO {tmp_name}'.format(enum=enum_name, tmp_name=tmp_name))

    new_type.create(op.get_bind())
    op.execute(alter_str.format(table='notifications', enum=enum_name))
    op.execute(alter_str.format(table='notification_history', enum=enum_name))

    op.execute('DROP TYPE ' + tmp_name)


def downgrade():
    op.execute('ALTER TYPE {enum} RENAME TO {tmp_name}'.format(enum=enum_name, tmp_name=tmp_name))

    # Convert 'sent' template into 'sending'
    update_str = "UPDATE {table} SET status='sending' where status='sent'"

    op.execute(update_str.format(table='notifications'))
    op.execute(update_str.format(table='notification_history'))

    old_type.create(op.get_bind())

    op.execute(alter_str.format(table='notifications', enum=enum_name))
    op.execute(alter_str.format(table='notification_history', enum=enum_name))

    op.execute('DROP TYPE ' + tmp_name)
