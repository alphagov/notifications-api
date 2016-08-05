"""empty message

Revision ID: 0046_organisations_and_branding
Revises: 0045_billable_units
Create Date: 2016-08-04 12:00:43.682610

"""

# revision identifiers, used by Alembic.
revision = '0046_organisations_and_branding'
down_revision = '0045_billable_units'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.create_table('branding_type',
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('name')
    )
    op.create_table('organisation',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('colour', sa.String(length=7), nullable=True),
        sa.Column('logo', sa.String(length=255), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.add_column('services', sa.Column('branding', sa.String(length=255)))
    op.add_column('services', sa.Column('organisation_id', postgresql.UUID(as_uuid=True)))
    op.add_column('services_history', sa.Column('branding', sa.String(length=255)))
    op.add_column('services_history', sa.Column('organisation_id', postgresql.UUID(as_uuid=True)))

    op.execute("INSERT INTO branding_type VALUES ('govuk'), ('org'), ('both')")
    # insert UKVI data as initial test data. hex and crest pulled from alphagov/whitehall
    op.execute("""INSERT INTO organisation VALUES (
        '9d25d02d-2915-4e98-874b-974e123e8536',
        '#9325b2',
        'ho_crest_27px_x2.png',
        'UK Visas and Immigration'
    )""")
    op.execute("UPDATE services SET branding='govuk'")
    op.execute("UPDATE services_history SET branding='govuk'")

    op.alter_column('services', 'branding', nullable=False)
    op.alter_column('services_history', 'branding', nullable=False)

    op.create_index(op.f('ix_services_branding'), 'services', ['branding'], unique=False)
    op.create_index(op.f('ix_services_organisation_id'), 'services', ['organisation_id'], unique=False)
    op.create_index(op.f('ix_services_history_branding'), 'services_history', ['branding'], unique=False)
    op.create_index(op.f('ix_services_history_organisation_id'), 'services_history', ['organisation_id'], unique=False)

    op.create_foreign_key(None, 'services', 'branding_type', ['branding'], ['name'])
    op.create_foreign_key(None, 'services', 'organisation', ['organisation_id'], ['id'])


def downgrade():
    op.drop_column('services_history', 'organisation_id')
    op.drop_column('services_history', 'branding')
    op.drop_column('services', 'organisation_id')
    op.drop_column('services', 'branding')
    op.drop_table('organisation')
    op.drop_table('branding_type')
