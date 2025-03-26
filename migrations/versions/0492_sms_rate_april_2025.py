"""
Create Date: 2025-03-26 14:13:45.410295
"""

import uuid

from alembic import op

revision = '0492_sms_rate_april_2025'
down_revision = '0491_letter_rates_april_2025'


def upgrade():
    op.execute(
        "INSERT INTO rates (id, valid_from, rate, notification_type) "
        f"VALUES('{uuid.uuid4()}', '2025-03-31 23:00:00', 0.0233, 'sms')"
    )


def downgrade():
    """
    We'll want to check and run downgrades manually since this will involve decisions
    about billing for any messages sent with the rates that have been removed.
    """
