"""

Revision ID: 0425_unique_service_name_2
Revises: 0424_n_history_created_at
Create Date: 2023-09-01 10:10:19.011060

"""

from alembic import op
import sqlalchemy as sa


revision = "0425_unique_service_name_2"
down_revision = "0424_n_history_created_at"


def upgrade():
    # run these commands with autocommit outside of a transaction - the main motivation for this is to
    # ensure we don't try and acquire access-exclusive locks (which the alter column commands need) on both the
    # services and services_history table at the same time, which can lead to deadlocks
    with op.get_context().autocommit_block():
        # update historical values
        op.execute("UPDATE services SET normalised_service_name = email_from WHERE normalised_service_name IS NULL")
        op.execute(
            "UPDATE services_history SET normalised_service_name = email_from WHERE normalised_service_name IS NULL"
        )

        op.alter_column("services", "normalised_service_name", existing_type=sa.VARCHAR(), nullable=False)
        op.alter_column("services_history", "normalised_service_name", existing_type=sa.VARCHAR(), nullable=False)

        op.alter_column("services", "email_from", existing_type=sa.VARCHAR(), nullable=True)
        op.alter_column("services_history", "email_from", existing_type=sa.VARCHAR(), nullable=True)

        op.drop_constraint("services_email_from_key", "services", type_="unique")


def downgrade():
    with op.get_context().autocommit_block():
        op.alter_column("services_history", "normalised_service_name", existing_type=sa.VARCHAR(), nullable=True)
        op.alter_column("services", "normalised_service_name", existing_type=sa.VARCHAR(), nullable=True)

        # back-fill any null email_from from normalised
        op.execute("UPDATE services SET email_from = normalised_service_name")
        op.execute("UPDATE services_history SET email_from = normalised_service_name")

        # now we can restore null constraint and unique index
        op.alter_column("services", "email_from", existing_type=sa.VARCHAR(), nullable=True)
        op.alter_column("services_history", "email_from", existing_type=sa.VARCHAR(), nullable=True)
        op.create_unique_constraint("services_email_from_key", "services", columns=["email_from"])
