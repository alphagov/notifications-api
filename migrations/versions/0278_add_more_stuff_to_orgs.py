"""

Revision ID: 0278_add_more_stuff_to_orgs
Revises: 0277_consent_to_research_null
Create Date: 2019-02-26 10:15:22.430340

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0278_add_more_stuff_to_orgs'
down_revision = '0277_consent_to_research_null'


def upgrade():
    op.create_table(
        'domain',
        sa.Column('domain', sa.String(length=255), nullable=False),
        sa.Column('organisation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['organisation_id'], ['organisation.id'], ),
        sa.PrimaryKeyConstraint('domain')
    )
    op.create_index(op.f('ix_domain_domain'), 'domain', ['domain'], unique=True)

    op.add_column('organisation', sa.Column('email_branding_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_organisation_email_branding_id', 'organisation', 'email_branding', ['email_branding_id'], ['id'])

    op.add_column('organisation', sa.Column('letter_branding_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_organisation_letter_branding_id', 'organisation', 'letter_branding', ['letter_branding_id'], ['id'])

    op.add_column('organisation', sa.Column('agreement_signed', sa.Boolean(), nullable=True))
    op.add_column('organisation', sa.Column('agreement_signed_at', sa.DateTime(), nullable=True))
    op.add_column('organisation', sa.Column('agreement_signed_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('organisation', sa.Column('agreement_signed_version', sa.Float(), nullable=True))
    op.add_column('organisation', sa.Column('crown', sa.Boolean(), nullable=True))
    op.add_column('organisation', sa.Column('organisation_type', sa.String(length=255), nullable=True))
    op.create_foreign_key('fk_organisation_agreement_user_id', 'organisation', 'users', ['agreement_signed_by_id'], ['id'])


def downgrade():
    op.drop_constraint('fk_organisation_agreement_user_id', 'organisation', type_='foreignkey')
    op.drop_column('organisation', 'organisation_type')
    op.drop_column('organisation', 'crown')
    op.drop_column('organisation', 'agreement_signed_version')
    op.drop_column('organisation', 'agreement_signed_by_id')
    op.drop_column('organisation', 'agreement_signed_at')
    op.drop_column('organisation', 'agreement_signed')

    op.drop_constraint('fk_organisation_email_branding_id', 'organisation', type_='foreignkey')
    op.drop_column('organisation', 'email_branding_id')

    op.drop_constraint('fk_organisation_letter_branding_id', 'organisation', type_='foreignkey')
    op.drop_column('organisation', 'letter_branding_id')

    op.drop_index(op.f('ix_domain_domain'), table_name='domain')
    op.drop_table('domain')
