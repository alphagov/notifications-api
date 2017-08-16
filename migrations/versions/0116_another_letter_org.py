"""empty message

Revision ID: 0116_another_letter_org
Revises: 0115_add_inbound_numbers
Create Date: 2017-06-29 12:44:16.815039

"""

# revision identifiers, used by Alembic.
revision = '0116_another_letter_org'
down_revision = '0115_add_inbound_numbers'

from alembic import op


def upgrade():
    op.execute("""
        INSERT INTO dvla_organisation VALUES
        ('005', 'Companies House')
    """)


def downgrade():
    # data migration, no downloads
    pass
