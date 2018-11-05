"""empty message

Revision ID: 0243_another_letter_org
Revises: 0242_template_folders

"""

# revision identifiers, used by Alembic.
revision = '0243_another_letter_org'
down_revision = '0242_template_folders'

from alembic import op


NEW_ORGANISATIONS = [
    ('516', 'Worcestershire County Council', 'worcestershire'),
    ('517', 'Buckinghamshire County Council', 'buckinghamshire'),
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
