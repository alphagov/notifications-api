"""empty message

Revision ID: 0105_opg_letter_org
Revises: 0104_more_letter_orgs
Create Date: 2017-06-29 12:44:16.815039

"""

# revision identifiers, used by Alembic.
revision = '0105_opg_letter_org'
down_revision = '0104_more_letter_orgs'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from flask import current_app


def upgrade():
    op.execute("""
        INSERT INTO dvla_organisation VALUES
        ('002', 'Office of the Public Guardian')
    """)


def downgrade():
    # data migration, no downloads
    pass
