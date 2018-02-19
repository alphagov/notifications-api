"""

Revision ID: 0166_add_org_user_stuff
Revises: 0165_another_letter_org
Create Date: 2018-02-14 17:25:11.747996

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0166_add_org_user_stuff'
down_revision = '0165_another_letter_org'


def upgrade():
    op.create_table('invite_status_type',
        sa.Column('name', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('name')
    )

    op.execute("insert into invite_status_type values ('pending'), ('accepted'), ('cancelled')")

    op.create_table('invited_organisation_users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email_address', sa.String(length=255), nullable=False),
        sa.Column('invited_by_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('organisation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),

        sa.ForeignKeyConstraint(['invited_by_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['organisation_id'], ['organisation.id'], ),
        sa.ForeignKeyConstraint(['status'], ['invite_status_type.name'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('user_to_organisation',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('organisation_id', postgresql.UUID(as_uuid=True), nullable=True),

        sa.ForeignKeyConstraint(['organisation_id'], ['organisation.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.UniqueConstraint('user_id', 'organisation_id', name='uix_user_to_organisation')
    )

    op.create_unique_constraint(None, 'organisation_to_service', columns=['service_id', 'organisation_id'])


def downgrade():
    op.drop_table('user_to_organisation')
    op.drop_table('invited_organisation_users')
    op.drop_table('invite_status_type')
