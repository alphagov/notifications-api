"""empty message

Revision ID: 0214_another_letter_org
Revises: 0213_brand_colour_domain_

"""

# revision identifiers, used by Alembic.
revision = '0214_another_letter_org'
down_revision = '0213_brand_colour_domain_'

from alembic import op


NEW_ORGANISATIONS = [
    ('510', 'Pension Wise'),
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
