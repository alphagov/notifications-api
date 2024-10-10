from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def enum_type_remove_value_step_1_create_new_enum(
    existing_enum_values: list[str], value_to_remove: str
) -> postgresql.ENUM:
    """
    If there any check constraints that use this column, they must be DROPPED beforehand and RECREATED afterwards
    """
    new_enum_values = existing_enum_values.copy()
    new_enum_values.remove(value_to_remove)
    enum_new = postgresql.ENUM(*new_enum_values, name=tmp_enum_name)

    pass


def enum_type_remove_value_step_2_update_columns(table: str, column: str, new_enum_type):
    """
    This acquires an ACCESS EXCLUSIVE lock so you should only one run of these in a
    single migration or you run the risk of deadlocks
    """
    pass


def enum_type_remove_value_step_3_remove_old_enum():
    pass


def add_type_to_enum(tables_and_columns: list[tuple[str, str]], existing_values: list[str], new_value: str = None):
    """
    tables_and_columns: a list of table-column pairs that use this enum, eg
        [("templates", "template_type"), ("templates_history", "template_type"), ...]

    existing_values: the existing values in the old enum
    new_values: the new values to add
    """
    conn = op.get_bind()
    conn.execute("ALTER TYPE template_type RENAME TO template_type_old;")
    template_type_new.create(conn)

    drop_check_constraints()

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
