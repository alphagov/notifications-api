"""

Revision ID: 0370_remove_reach
Revises: 0369_update_sms_rates
Create Date: 2022-04-27 16:00:00

"""

import itertools
import uuid
from datetime import datetime

from alembic import op
from sqlalchemy.sql import text

from app.models import LetterRate

revision = "0370_remove_reach"
down_revision = "0369_update_sms_rates"


def upgrade():
    conn = op.get_bind()
    conn.execute(text("DELETE FROM provider_details WHERE identifier = 'reach'"))


def downgrade():
    conn = op.get_bind()
    conn.execute(
        text(
            """
            INSERT INTO provider_details (
                id,
                display_name,
                identifier,
                priority,
                notification_type,
                active,
                version,
                created_by_id
            )
            VALUES (
                '{}',
                'Reach',
                'reach',
                0,
                'sms',
                false,
                1,
                null
            )
            """.format(
                str(uuid.uuid4()),
            )
        )
    )
