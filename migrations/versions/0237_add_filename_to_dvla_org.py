"""

Revision ID: 0237_add_filename_to_dvla_org
Revises: 0236_another_letter_org
Create Date: 2018-09-28 15:39:21.115358

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


revision = '0237_add_filename_to_dvla_org'
down_revision = '0236_another_letter_org'


LOGOS = {
    '001': 'hm-government',
    '002': 'opg',
    '003': 'dwp',
    '004': 'geo',
    '005': 'ch',
    '006': 'dwp-welsh',
    '007': 'dept-for-communities',
    '008': 'mmo',
    '009': 'hmpo',
    '500': 'hm-land-registry',
    '501': 'ea',
    '502': 'wra',
    '503': 'eryc',
    '504': 'rother',
    '505': 'cadw',
    '506': 'twfrs',
    '507': 'thames-valley-police',
    '508': 'ofgem',
    '509': 'hackney',
    '510': 'pension-wise',
    '511': 'nhs',
    '512': 'vale-of-glamorgan',
    '513': 'wdc',
    '514': 'brighton-hove',
}


def upgrade():
    conn = op.get_bind()
    op.add_column('dvla_organisation', sa.Column('filename', sa.String(length=255), nullable=True))

    for org_id, org_filename in LOGOS.items():
        conn.execute(text("""
            UPDATE dvla_organisation SET filename = :filename WHERE id = :id
        """), filename=org_filename, id=org_id)


def downgrade():
    op.drop_column('dvla_organisation', 'filename')
