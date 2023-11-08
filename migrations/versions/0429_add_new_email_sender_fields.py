"""

Revision ID: 0429_add_new_email_sender_fields
Revises: 0428_letter_rates_errata
Create Date: 2023-10-16 15:46:30.137552

"""
from alembic import op
import sqlalchemy as sa


revision = "0429_add_new_email_sender_fields"
down_revision = "0428_letter_rates_errata"


def upgrade():
    op.add_column("services", sa.Column("custom_email_sender_name", sa.String(length=255), nullable=True))
    op.add_column("services", sa.Column("email_sender_local_part", sa.String(length=255), nullable=True))
    op.add_column("services_history", sa.Column("custom_email_sender_name", sa.String(length=255), nullable=True))
    op.add_column("services_history", sa.Column("email_sender_local_part", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("services_history", "email_sender_local_part")
    op.drop_column("services_history", "custom_email_sender_name")
    op.drop_column("services", "email_sender_local_part")
    op.drop_column("services", "custom_email_sender_name")
