"""empty message

Revision ID: 0017_add_failure_types
Revises: 0016_reply_to_email
Create Date: 2016-05-17 11:23:36.881219

"""

# revision identifiers, used by Alembic.
revision = '0017_add_failure_types'
down_revision = '0016_reply_to_email'

from alembic import op
import sqlalchemy as sa


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    status_type = sa.Enum('sending', 'delivered', 'failed',
                          'technical-failure', 'temporary-failure', 'permanent-failure',
                          name='notification_status_type')
    status_type.create(op.get_bind())
    op.add_column('notifications', sa.Column('new_status', status_type, nullable=True))
    op.execute('update notifications set new_status = CAST(CAST(status as text) as notification_status_type)')
    op.alter_column('notifications', 'status', new_column_name='old_status')
    op.alter_column('notifications', 'new_status', new_column_name='status')
    op.drop_column('notifications', 'old_status')
    op.get_bind()
    op.execute('DROP TYPE notification_status_types')
    op.alter_column('notifications', 'status', nullable=False)


def downgrade():
    status_type = sa.Enum('sending', 'delivered', 'failed',
                          name='notification_status_types')
    status_type.create(op.get_bind())
    op.add_column('notifications', sa.Column('old_status', status_type, nullable=True))

    op.execute("update notifications set status = 'failed' where status in ('technical-failure', 'temporary-failure', 'permanent-failure')")
    op.execute('update notifications set old_status = CAST(CAST(status as text) as notification_status_types)')
    op.alter_column('notifications', 'status', new_column_name='new_status')
    op.alter_column('notifications', 'old_status', new_column_name='status')
    op.drop_column('notifications', 'new_status')
    op.get_bind()
    op.execute('DROP TYPE notification_status_type')
    op.alter_column('notifications', 'status', nullable=False)