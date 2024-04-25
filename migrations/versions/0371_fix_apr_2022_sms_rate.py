"""

Revision ID: 0371_fix_apr_2022_sms_rate
Revises: 0370_remove_reach
Create Date: 2022-04-26 09:39:45.260951

"""

import uuid

from alembic import op

revision = "0371_fix_apr_2022_sms_rate"
down_revision = "0370_remove_reach"


def upgrade():
    op.execute(
        "INSERT INTO rates(id, valid_from, rate, notification_type) "
        f"VALUES('{uuid.uuid4()}', '2022-03-31 23:00:00', 0.0161, 'sms')"
    )
    op.execute(
        """
        UPDATE ft_billing
        SET rate = 0.0161
        WHERE
        notification_type = 'sms' AND
        bst_date >= '2022-04-01' AND
        bst_date < '2022-05-01'
        """
    )


def downgrade():
    pass
