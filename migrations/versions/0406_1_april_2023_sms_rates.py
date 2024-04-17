"""

Revision ID: 0406_1_april_2023_sms_rates
Revises: 0405_template_formatting_flags
Create Date: 2023-03-06 11:32:20.588364

"""

import uuid

from alembic import op


revision = "0406_1_april_2023_sms_rates"
down_revision = "0405_template_formatting_flags"


def upgrade():
    op.execute(
        "INSERT INTO rates(id, valid_from, rate, notification_type) "
        f"VALUES('{uuid.uuid4()}', '2023-03-31 23:00:00', 0.0197, 'sms')"
    )


def downgrade():
    pass
