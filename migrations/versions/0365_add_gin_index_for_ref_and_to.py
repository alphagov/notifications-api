"""

Revision ID: 0365_add_gin_index_ref_and_to
Revises: 0364_drop_old_column

Create Date: 2022-02-14 11:16:27.750234

"""
import os

from alembic import op

revision = '0365_add_gin_index_ref_and_to'
down_revision = '0364_drop_old_column'
environment = os.environ['NOTIFY_ENVIRONMENT']


def upgrade():
    if environment not in ["live", "production"]:
      conn = op.get_bind()
      conn.execute("""
          CREATE INDEX ix_notifications_get_by_recipient_or_reference ON
          notifications USING GIN
          (normalised_to gin_trgm_ops, client_reference gin_trgm_ops)
      """)


def downgrade():
    if environment not in ["live", "production"]:
      conn = op.get_bind()
      conn.execute("""
          DROP INDEX ix_notifications_get_by_recipient_or_reference
      """)
