"""empty message

Revision ID: 0251_another_letter_org
Revises: 0250_drop_stats_template_table

"""

# revision identifiers, used by Alembic.
revision = '0251_another_letter_org'
down_revision = '0250_drop_stats_template_table'

from alembic import op


NEW_ORGANISATIONS = [
    ('522', 'Anglesey Council', 'anglesey'),
    ('523', 'Angus Council', 'angus'),
    ('524', 'Cheshire East Council', 'cheshire-east'),
    ('525', 'Newham Council', 'newham'),
    ('526', 'Warwickshire Council', 'warwickshire'),
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
