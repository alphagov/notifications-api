"""empty message

Revision ID: 0117_international_sms_notify
Revises: 0116_another_letter_org
Create Date: 2017-08-29 14:09:41.042061

"""

# revision identifiers, used by Alembic.
revision = "0117_international_sms_notify"
down_revision = "0116_another_letter_org"

from datetime import UTC, datetime

from alembic import op

NOTIFY_SERVICE_ID = "d6aa2c68-a2d9-4437-ab19-3ae8eb202553"


def upgrade():
    op.execute(
        """
        INSERT INTO service_permissions VALUES
        ('{}', 'international_sms', '{}')
    """.format(
            NOTIFY_SERVICE_ID, datetime.now(UTC).replace(tzinfo=None)
        )
    )


def downgrade():
    op.execute(
        """
        DELETE FROM service_permissions
            WHERE
                service_id = '{}' AND
                permission = 'international_sms'
    """.format(
            NOTIFY_SERVICE_ID
        )
    )
