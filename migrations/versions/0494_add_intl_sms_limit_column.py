"""
Create Date: 2025-04-09 17:37:32.633786
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0494_add_intl_sms_limit_column'
down_revision = '0493_unique_org_permissions'


def upgrade():
    op.add_column('services', sa.Column('international_sms_message_limit', sa.BigInteger(), nullable=False, server_default="250000"))
    op.add_column(
        "services_history",
        sa.Column(
            "international_sms_message_limit",
            sa.BigInteger(),
            nullable=False,
            server_default="250000",
        ),
    )


def downgrade():
    op.drop_column('services_history', 'international_sms_message_limit')
    op.drop_column('services', 'international_sms_message_limit')
