"""

Revision ID: 0230_noti_postage_constraint_2
Revises: 0230_noti_postage_constraint_1
Create Date: 2018-09-19 11:42:52.229430

"""
from alembic import op


revision = '0230_noti_postage_constraint_2'
down_revision = '0230_noti_postage_constraint_1'


def upgrade():
    op.execute("""
        ALTER TABLE notification_history ADD CONSTRAINT "chk_notification_history_postage_null"
        CHECK (
            CASE WHEN notification_type = 'letter' THEN
                postage is not null and postage in ('first', 'second')
            ELSE
                postage is null
            END
        )
        NOT VALID
    """)


def downgrade():
    op.drop_constraint('chk_notification_history_postage_null', 'notification_history', type_='check')
