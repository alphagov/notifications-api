"""empty message

Revision ID: 0070_fix_notify_user_email
Revises: 0069_add_dvla_job_status
Create Date: 2017-03-10 16:15:22.153948

"""

# revision identifiers, used by Alembic.
revision = '0070_fix_notify_user_email'
down_revision = '0069_add_dvla_job_status'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.execute("""
        UPDATE users
        SET email_address = 'notify-service-user@digital.cabinet-office.gov.uk'
        WHERE email_address = 'notify-service-user@digital.cabinet-office'
    """)


def downgrade():
    op.execute("""
        UPDATE users
        SET email_address = 'notify-service-user@digital.cabinet-office'
        WHERE email_address = 'notify-service-user@digital.cabinet-office.gov.uk'
    """)
