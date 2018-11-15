"""empty message

Revision ID: 0244_another_letter_org
Revises: 0243_another_letter_org

"""

# revision identifiers, used by Alembic.
revision = '0244_another_letter_org'
down_revision = '0243_another_letter_org'

from alembic import op


NEW_ORGANISATIONS = [
    ('518', 'Bournemouth Borough Council', 'bournemouth'),
    ('519', 'Hampshire County Council', 'hants'),
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
