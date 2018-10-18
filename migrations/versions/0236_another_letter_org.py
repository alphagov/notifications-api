"""empty message

Revision ID: 0236_another_letter_org
Revises: 0235_add_postage_to_pk

"""

# revision identifiers, used by Alembic.
revision = '0236_another_letter_org'
down_revision = '0235_add_postage_to_pk'

from alembic import op


NEW_ORGANISATIONS = [
    ('514', 'Brighton and Hove city council'),
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
