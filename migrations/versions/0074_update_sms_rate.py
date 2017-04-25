"""empty message

Revision ID: 0074_update_sms_rate
Revises: 0073_add_international_sms_flag
Create Date: 2017-04-24 12:10:02.116278

"""

import uuid

revision = '0074_update_sms_rate'
down_revision = '0073_add_international_sms_flag'

from alembic import op


def upgrade():
    op.get_bind()
    op.execute("INSERT INTO provider_rates (id, valid_from, rate, provider_id) "
               "VALUES ('{}', '2017-04-01 00:00:00', 1.58, "
               "(SELECT id FROM provider_details WHERE identifier = 'mmg'))".format(uuid.uuid4())
               )


def downgrade():
    op.get_bind()
    op.execute("DELETE FROM provider_rates where valid_from = '2017-04-01 00:00:00' "
               "and provider_id = (SELECT id FROM provider_details WHERE identifier = 'mmg')")