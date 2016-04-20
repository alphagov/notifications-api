"""empty message

Revision ID: 0004_notification_stats_date
Revises: 0003_add_service_history
Create Date: 2016-04-20 13:59:01.132535

"""

# revision identifiers, used by Alembic.
revision = '0004_notification_stats_date'
down_revision = '0003_add_service_history'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint('uix_service_to_day', 'notification_statistics')
    op.alter_column('notification_statistics', 'day', new_column_name='day_string')
    op.add_column('notification_statistics', sa.Column('day', sa.Date(), nullable=True))

    op.get_bind()
    op.execute("UPDATE notification_statistics ns1 SET day = (SELECT to_date(day_string, 'YYYY-MM-DD') FROM notification_statistics ns2 WHERE ns1.id = ns2.id)")

    op.alter_column('notification_statistics', 'day', nullable=False)
    op.create_index(op.f('ix_notification_statistics_day'), 'notification_statistics', ['day'], unique=False)
    op.drop_column('notification_statistics', 'day_string')
    op.create_unique_constraint('uix_service_to_day', 'notification_statistics', columns=['service_id', 'day'])

    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_notification_statistics_day'), table_name='notification_statistics')
    op.drop_constraint('uix_service_to_day', 'notification_statistics')

    op.alter_column('notification_statistics', 'day', new_column_name='day_date')
    op.add_column('notification_statistics', sa.Column('day', sa.String(), nullable=True))

    op.get_bind()
    op.execute("UPDATE notification_statistics ns1 SET day = (SELECT to_char(day_date, 'YYYY-MM-DD') FROM notification_statistics ns2 WHERE ns1.id = ns2.id)")

    op.alter_column('notification_statistics', 'day', nullable=False)
    op.drop_column('notification_statistics', 'day_date')
    op.create_unique_constraint('uix_service_to_day', 'notification_statistics', columns=['service_id', 'day'])

    ### end Alembic commands ###
