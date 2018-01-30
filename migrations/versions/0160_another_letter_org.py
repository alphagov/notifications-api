"""empty message

Revision ID: 0160_another_letter_org
Revises: 0159_add_historical_redact
Create Date: 2017-06-29 12:44:16.815039

"""

# revision identifiers, used by Alembic.
revision = '0160_another_letter_org'
down_revision = '0159_add_historical_redact'

from alembic import op


NEW_ORGANISATIONS = [
    ('501', 'Environment Agency (PDF letters ONLY)'),
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
