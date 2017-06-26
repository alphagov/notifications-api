"""empty message

Revision ID: 0101_een_logo
Revises: 0100_notification_created_by
Create Date: 2017-06-26 11:43:30.374723

"""

from alembic import op

revision = '0101_een_logo'
down_revision = '0100_notification_created_by'


ENTERPRISE_EUROPE_NETWORK_ID = '89ce468b-fb29-4d5d-bd3f-d468fb6f7c36'


def upgrade():
    op.execute("""INSERT INTO organisation VALUES (
        '{}',
        '',
        'een_x2.png',
        ''
    )""".format(ENTERPRISE_EUROPE_NETWORK_ID))


def downgrade():
    op.execute("""
        DELETE FROM organisation WHERE "id" = '{}'
    """.format(ENTERPRISE_EUROPE_NETWORK_ID))
