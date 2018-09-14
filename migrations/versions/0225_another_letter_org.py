"""empty message

Revision ID: 0225_another_letter_org
Revises: 0224_returned_letter_status

"""

# revision identifiers, used by Alembic.
revision = '0225_another_letter_org'
down_revision = '0224_returned_letter_status'

from alembic import op


NEW_ORGANISATIONS = [
    ('512', 'Vale of Glamorgan'),
    ('513', 'Rother and Wealden'),
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
