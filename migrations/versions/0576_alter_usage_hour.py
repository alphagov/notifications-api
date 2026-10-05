"""
Create Date: 2026-10-04 14:38:20.775530
"""

from alembic import op

revision = '0576_alter_usage_hour'
down_revision = '0575_invusr_srv_id_null_valid'


def upgrade():
    if op.get_context().as_sql:
        op.get_context().impl.static_output("-- squawk-ignore-file changing-column-type, prefer-timestamp-tz")

    op.execute(
        """
        ALTER TABLE api_key_usage
        ALTER COLUMN usage_hour TYPE timestamp without time zone
        """
    )

def downgrade():
    op.execute(
        """
        ALTER TABLE api_key_usage
        ALTER COLUMN usage_hour TYPE timestamptz 
        """
    )