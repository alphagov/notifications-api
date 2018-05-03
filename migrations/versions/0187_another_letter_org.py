"""empty message

Revision ID: 0187_another_letter_org
Revises: 0186_rename_is_active_columns
Create Date: 2017-06-29 12:44:16.815039

"""

# revision identifiers, used by Alembic.
revision = '0187_another_letter_org'
down_revision = '0186_rename_is_active_columns'

from alembic import op


NEW_ORGANISATIONS = [
    ('505', 'CADW'),
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
