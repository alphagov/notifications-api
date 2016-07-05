"""0038_test_api_key_type

Revision ID: 0038_test_api_key_type
Revises: 0037_service_sms_sender
Create Date: 2016-07-05 10:28:12.947306

"""

# revision identifiers, used by Alembic.
revision = '0038_test_api_key_type'
down_revision = '0037_service_sms_sender'

from alembic import op


def upgrade():
    op.execute("insert into key_types values ('test')")


def downgrade():
    op.execute("update notifications set key_type = 'normal' where key_type = 'test'")
    op.execute("update api_keys set key_type = 'normal' where key_type = 'test'")
    op.execute("delete from key_types where name='test'")
