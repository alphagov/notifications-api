"""empty message

Revision ID: 0074_add_intl_provider_mmg
Revises: 0073_add_international_sms_flag
Create Date: 2017-04-24 12:39:04.102479

"""

# revision identifiers, used by Alembic.
from datetime import datetime
import uuid

from alembic import op
import sqlalchemy as sa

revision = '0074_add_intl_provider_mmg'
down_revision = '0073_add_international_sms_flag'


def upgrade():
    op.add_column('provider_details', sa.Column('provider_type', sa.String(length=255), nullable=False, server_default='domestic'))
    op.add_column('provider_details_history', sa.Column('provider_type', sa.String(length=255), nullable=False, server_default='domestic'))

    mmg_intl_provider_id = str(uuid.uuid4())
    provider_details_insert = """
        INSERT INTO provider_details (id, display_name, identifier, priority, notification_type, active, version, provider_type)
        VALUES ('{}', 'MMG International', 'mmg-intl', 10, 'sms', false, 1, 'international')
    """
    provider_details_history_insert = """
        INSERT INTO provider_details_history (id, display_name, identifier, priority, notification_type, active, version, provider_type)
        VALUES ('{}', 'MMG International', 'mmg-intl', 10, 'sms', false, 1, 'international')
    """

    op.execute(provider_details_insert.format(mmg_intl_provider_id))
    op.execute(provider_details_history_insert.format(mmg_intl_provider_id))


def downgrade():
    op.drop_column('provider_details', 'provider_type')
    op.drop_column('provider_details_history', 'provider_type')
    op.execute("DELETE FROM provider_details WHERE identifier = 'mmg-intl'")
    op.execute("DELETE FROM provider_details_history WHERE identifier = 'mmg-intl'")
