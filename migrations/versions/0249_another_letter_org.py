"""empty message

Revision ID: 0249_another_letter_org
Revises: 0248_enable_choose_postage

"""

# revision identifiers, used by Alembic.
revision = '0249_another_letter_org'
down_revision = '0248_enable_choose_postage'

from alembic import op


NEW_ORGANISATIONS = [
    ('521', 'North Somerset Council', 'north-somerset'),
]


def upgrade():
    for numeric_id, name, filename in NEW_ORGANISATIONS:
        op.execute("""
            INSERT
                INTO dvla_organisation
                VALUES ('{}', '{}', '{}')
        """.format(numeric_id, name, filename))


def downgrade():
    for numeric_id, _, _ in NEW_ORGANISATIONS:
        op.execute("""
            DELETE
                FROM dvla_organisation
                WHERE id = '{}'
        """.format(numeric_id))
