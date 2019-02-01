"""empty message

Revision ID: 0255_another_letter_org
Revises: 0254_folders_for_all

"""

# revision identifiers, used by Alembic.
revision = '0255_another_letter_org'
down_revision = '0254_folders_for_all'

from alembic import op


NEW_ORGANISATIONS = [
    ('010', 'Disclosure and Barring Service', 'dbs'),
    ('527', 'Natural Resources Wales', 'natural-resources-wales'),
    ('528', 'North Yorkshire Council', 'north-yorkshire'),
    ('529', 'Redbridge Council', 'redbridge'),
    ('530', 'Wigan Council', 'wigan'),
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
