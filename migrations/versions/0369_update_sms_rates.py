"""

Revision ID: 0369_update_sms_rates
Revises: 0368_move_orgs_to_nhs_branding
Create Date: 2022-04-26 09:39:45.260951

"""

import uuid

from alembic import op

revision = "0369_update_sms_rates"
down_revision = "0368_move_orgs_to_nhs_branding"


def upgrade():
    op.execute(
        "INSERT INTO rates(id, valid_from, rate, notification_type) "
        f"VALUES('{uuid.uuid4()}', '2022-04-30 23:00:00', 0.0172, 'sms')"
    )


def downgrade():
    pass
