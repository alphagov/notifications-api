"""empty message

Revision ID: 0241_another_letter_org
Revises: 0240_dvla_org_non_nullable

"""

# revision identifiers, used by Alembic.
revision = '0241_another_letter_org'
down_revision = '0240_dvla_org_non_nullable'

from alembic import op


NEW_ORGANISATIONS = [
    ('515', 'ACAS', 'acas'),
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
