"""empty message

Revision ID: 0047_ukvi_spelling
Revises: 0046_organisations_and_branding
Create Date: 2016-08-22 16:06:32.981723

"""

# revision identifiers, used by Alembic.
revision = '0047_ukvi_spelling'
down_revision = '0046_organisations_and_branding'

from alembic import op


def upgrade():
    op.execute("""
        UPDATE organisation
        SET name = 'UK Visas & Immigration'
        WHERE id = '9d25d02d-2915-4e98-874b-974e123e8536'
    """)


def downgrade():
    op.execute("""
        UPDATE organisation
        SET name = 'UK Visas and Immigration'
        WHERE id = '9d25d02d-2915-4e98-874b-974e123e8536'
    """)
