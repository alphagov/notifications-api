"""empty message

Revision ID: 0088_letter_billing
Revises: 0087_scheduled_notifications
Create Date: 2017-05-31 11:43:55.744631

"""
import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0088_letter_billing'
down_revision = '0087_scheduled_notifications'


def upgrade():
    op.create_table('letter_rates',
                    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('valid_from', sa.DateTime(), nullable=False),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_table('letter_rate_details',
                    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('letter_rate_id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('page_total', sa.Integer(), nullable=False),
                    sa.Column('rate', sa.Numeric(), nullable=False),
                    sa.ForeignKeyConstraint(['letter_rate_id'], ['letter_rates.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_letter_rate_details_letter_rate_id'), 'letter_rate_details', ['letter_rate_id'],
                    unique=False)

    op.get_bind()
    letter_id = uuid.uuid4()
    op.execute("insert into letter_rates(id, valid_from) values('{}', '2017-03-31 23:00:00')".format(letter_id))
    insert_details = "insert into letter_rate_details(id, letter_rate_id, page_total, rate) values('{}', '{}', {}, {})"
    op.execute(
        insert_details.format(uuid.uuid4(), letter_id, 1, 29.3))
    op.execute(
        insert_details.format(uuid.uuid4(), letter_id, 2, 32))
    op.execute(
        insert_details.format(uuid.uuid4(), letter_id, 3, 35))


def downgrade():
    op.get_bind()
    op.drop_index('ix_letter_rate_details_letter_rate_id')
    op.drop_table('letter_rate_details')
    op.drop_table('letter_rates')
