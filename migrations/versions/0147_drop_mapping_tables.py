"""

Revision ID: 0147_drop_mapping_tables
Revises: 0146_add_service_callback_api
Create Date: 2017-11-30 15:48:44.588438

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0147_drop_mapping_tables'
down_revision = '0146_add_service_callback_api'


def upgrade():
    op.drop_table('notification_to_sms_sender')
    op.drop_table('notification_to_email_reply_to')


def downgrade():
    op.create_table('notification_to_email_reply_to',
                    sa.Column('notification_id', postgresql.UUID(), autoincrement=False, nullable=False),
                    sa.Column('service_email_reply_to_id', postgresql.UUID(), autoincrement=False, nullable=False),
                    sa.ForeignKeyConstraint(['notification_id'], ['notifications.id'],
                                            name='notification_to_email_reply_to_notification_id_fkey'),
                    sa.ForeignKeyConstraint(['service_email_reply_to_id'], ['service_email_reply_to.id'],
                                            name='notification_to_email_reply_to_service_email_reply_to_id_fkey'),
                    sa.PrimaryKeyConstraint('notification_id', 'service_email_reply_to_id',
                                            name='notification_to_email_reply_to_pkey')
                    )
    op.create_table('notification_to_sms_sender',
                    sa.Column('notification_id', postgresql.UUID(), autoincrement=False, nullable=False),
                    sa.Column('service_sms_sender_id', postgresql.UUID(), autoincrement=False, nullable=False),
                    sa.ForeignKeyConstraint(['notification_id'], ['notifications.id'],
                                            name='notification_to_sms_sender_notification_id_fkey'),
                    sa.ForeignKeyConstraint(['service_sms_sender_id'], ['service_sms_senders.id'],
                                            name='notification_to_sms_sender_service_sms_sender_id_fkey'),
                    sa.PrimaryKeyConstraint('notification_id', 'service_sms_sender_id',
                                            name='notification_to_sms_sender_pkey')
                    )
