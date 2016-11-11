"""
we weren't previously using the services.active column , and by default it was set to false. lets set all services to
active, so that in the future we can turn it off to signify deactivating a service

Revision ID: 0059_set_services_to_active
Revises: 0058_add_letters_flag
Create Date: 2016-10-31 15:17:16.716450

"""

# revision identifiers, used by Alembic.
revision = '0059_set_services_to_active'
down_revision = '0058_add_letters_flag'

from alembic import op


def upgrade():
    op.execute('UPDATE services SET active = TRUE')


def downgrade():
    op.execute('UPDATE services SET active = FALSE')
