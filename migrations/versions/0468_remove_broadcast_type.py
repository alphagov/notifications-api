"""
Create Date: 2024-10-01 11:08:46.900469
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0468_remove_broadcast_type"
down_revision = "0467_remove_broadcast_perms"


template_type_new_values = ["email", "sms", "letter"]
template_type_new = postgresql.ENUM(*template_type_new_values, name="template_type")


def drop_check_constraints():
    op.drop_constraint("chk_templates_letter_languages", "templates")
    op.drop_constraint("chk_templates_history_letter_languages", "templates_history")

    op.drop_constraint("ck_templates_letter_attachments", "templates")
    op.drop_constraint("ck_templates_history_letter_attachments", "templates_history")

    op.drop_constraint("ck_templates_non_email_has_unsubscribe_false", "templates")
    op.drop_constraint("ck_templates_history_non_email_has_unsubscribe_false", "templates_history")


def add_check_constraints():
    op.create_check_constraint(
        "chk_templates_letter_languages",
        "templates",
        """
        CASE WHEN template_type = 'letter' THEN
            letter_languages is not null
        ELSE
            letter_languages is null
        END
        """,
        postgresql_not_valid=True,
    )
    op.create_check_constraint(
        "chk_templates_history_letter_languages",
        "templates_history",
        """
        CASE WHEN template_type = 'letter' THEN
            letter_languages is not null
        ELSE
            letter_languages is null
        END
        """,
        postgresql_not_valid=True,
    )

    op.create_check_constraint(
        "ck_templates_letter_attachments",
        "templates",
        "template_type = 'letter' OR letter_attachment_id IS NULL",
        postgresql_not_valid=True,
    )
    op.create_check_constraint(
        "ck_templates_history_letter_attachments",
        "templates_history",
        "template_type = 'letter' OR letter_attachment_id IS NULL",
        postgresql_not_valid=True,
    )

    op.create_check_constraint(
        "ck_templates_non_email_has_unsubscribe_false",
        "templates",
        "template_type = 'email' OR has_unsubscribe_link IS false",
        postgresql_not_valid=True,
    )
    op.create_check_constraint(
        "ck_templates_history_non_email_has_unsubscribe_false",
        "templates_history",
        "template_type = 'email' OR has_unsubscribe_link IS false",
        postgresql_not_valid=True,
    )


def upgrade():
    """
    there are three check constraints on the template_type column (across both templates and templates_history).

    These check constraints say things like "if type == 'letter'" - this is an enum comparison, so if we change the
    type of the column, we get an error

    > (psycopg2.errors.UndefinedFunction) operator does not exist: template_type = template_type_old
    > HINT:  No operator matches the given name and argument types. You might need to add explicit type casts.

    This appears confusing because we're passing in a `using` clause to tell postgres exactly how to do this, but
    this using clause only applies to the column type, and not other usages of that column within the check constraints.

    To get round this, we "simply" drop all the constraints and then recreate them afterwards, referring to the new
    """
    conn = op.get_bind()
    conn.execute("ALTER TYPE template_type RENAME TO template_type_old;")
    template_type_new.create(conn)

    drop_check_constraints()

    # TODO: split into three separate migrations. figure out downgrade steps.
    op.alter_column(
        table_name="templates",
        column_name="template_type",
        type_=template_type_new,
        postgresql_using="template_type::text::template_type",
    )
    op.alter_column(
        table_name="templates_history",
        column_name="template_type",
        type_=template_type_new,
        postgresql_using="template_type::text::template_type",
    )
    op.alter_column(
        table_name="service_contact_list",
        column_name="template_type",
        type_=template_type_new,
        postgresql_using="template_type::text::template_type",
    )

    conn.execute("DROP TYPE template_type_old;")
    # note: need to revalidate these constraints in a separate migration to avoid a lengthy access exclusive lock
    add_check_constraints()


def downgrade():
    # don't need to do the constraints dance, or the enum type dance, when adding a new value

    # ALTER TYPE must be run outside of a transaction block (see link below for details)
    # https://alembic.sqlalchemy.org/en/latest/api/runtime.html#alembic.runtime.migration.MigrationContext.autocommit_block
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE template_type ADD VALUE 'broadcast'")
