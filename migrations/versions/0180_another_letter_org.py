"""empty message

Revision ID: 0180_another_letter_org
Revises: 0179_billing_primary_const
Create Date: 2017-06-29 12:44:16.815039

"""

# revision identifiers, used by Alembic.
revision = '0180_another_letter_org'
down_revision = '0179_billing_primary_const'

from alembic import op


NEW_ORGANISATIONS = [
    ('504', 'Rother District Council'),
]


def upgrade():
    for numeric_id, name in NEW_ORGANISATIONS:
        op.execute("""
            INSERT
                INTO dvla_organisation
                VALUES ('{}', '{}')
        """.format(numeric_id, name))


def downgrade():
    for numeric_id, _ in NEW_ORGANISATIONS:
        op.execute("""
            DELETE
                FROM dvla_organisation
                WHERE id = '{}'
        """.format(numeric_id))
