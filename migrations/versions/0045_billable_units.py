"""empty message

Revision ID: 0045_billable_units
Revises: 0044_jobs_to_notification_hist
Create Date: 2016-08-02 16:36:42.455838

"""

# revision identifiers, used by Alembic.
revision = '0045_billable_units'
down_revision = '0044_jobs_to_notification_hist'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm.session import Session

from app.models import Service

def upgrade():
    op.add_column('notifications', sa.Column('billable_units', sa.Integer()))
    op.add_column('notification_history', sa.Column('billable_units', sa.Integer()))

    op.execute('update notifications set billable_units = 0')
    op.execute('update notification_history set billable_units = 0')

    op.alter_column('notifications', 'billable_units', nullable=False)
    op.alter_column('notification_history', 'billable_units', nullable=False)


    conn = op.get_bind()

    # caveats
    # only adjusts notifications for services that have never been in research mode. On live, research mode was
    # limited to only services that we have set up ourselves so deemed this acceptable.
    billable_services = conn.execute('''
        SELECT id FROM services_history WHERE id not in (select id from services_history where research_mode)
    ''')
    # set to 'null' if there are no billable services so we do not get a syntax error in the update statement
    service_ids = ','.join("'{}'".format(service.id) for service in billable_services) or 'null'


    update_statement = '''
        UPDATE {}
        SET billable_units = (
            CASE
                WHEN content_char_count <= 160 THEN 1
                ELSE ceil(content_char_count::float / 153::float)
            END
        )
        WHERE content_char_count is not null
        AND service_id in ({})
        AND notification_type = 'sms'
    '''

    conn = op.get_bind()
    conn.execute(update_statement.format('notifications', service_ids))
    conn.execute(update_statement.format('notification_history', service_ids))
    op.drop_column('notifications', 'content_char_count')
    op.drop_column('notification_history', 'content_char_count')


def downgrade():
    op.add_column('notifications', sa.Column(
        'content_char_count',
        sa.INTEGER(),
        autoincrement=False,
        nullable=True)
    )
    op.add_column('notification_history', sa.Column(
        'content_char_count',
        sa.INTEGER(),
        autoincrement=False,
        nullable=True)
    )

    conn = op.get_bind()

    # caveats
    # only adjusts notifications for services that have never been in research mode. On live, research mode was
    # limited to only services that we have set up ourselves
    billable_services = conn.execute('''
        SELECT id FROM services_history WHERE id not in (select id from services_history where research_mode)
    ''')
    # set to 'null' if there are no billable services so we do not get a syntax error in the update statement
    service_ids = ','.join("'{}'".format(service.id) for service in billable_services) or 'null'

    # caveats:
    # only approximates character counts - billable * 153 to get at least a decent ballpark
    # research mode messages assumed to be one message length
    update_statement = '''
        UPDATE {}
        SET content_char_count = GREATEST(billable_units, 1) * 150
        WHERE service_id in ({})
        AND notification_type = 'sms'
    '''

    conn = op.get_bind()
    conn.execute(update_statement.format('notifications', service_ids))
    conn.execute(update_statement.format('notification_history', service_ids))
    op.drop_column('notifications', 'billable_units')
    op.drop_column('notification_history', 'billable_units')
