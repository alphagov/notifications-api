"""

Revision ID: 0387_migrate_alt_text
Revises: 0386_email_branding_alt_text
Create Date: 2022-11-21 19:05:49.047224

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0387_migrate_alt_text"
down_revision = "0386_email_branding_alt_text"


def upgrade():
    conn = op.get_bind()
    # there are some old email_branding rows with empty string. Keep them as null.
    conn.execute(
        sa.text(
            """
            UPDATE
                email_branding
            SET
                text = null
            WHERE
                text = '';
            """
        )
    )
    # if text is null, we need alt_text, so infer it from the branding name instead
    conn.execute(
        sa.text(
            """
            UPDATE
                email_branding
            SET
                alt_text = name
            WHERE
                text is null;
            """
        )
    )
    # any rows with alt_text and text, remove alt_text.
    # i don't expect any rows to be set like this yet, but lets just ensure the constraint creation wont fail
    conn.execute(
        sa.text(
            """
            UPDATE
                email_branding
            SET
                alt_text = null
            WHERE
                text is not null;
            """
        )
    )
    op.create_check_constraint(
        "ck_email_branding_one_of_alt_text_or_text_is_null",
        "email_branding",
        """
        (text is not null and alt_text is null) or
        (text is null and alt_text is not null)
        """,
    )


def downgrade():
    op.drop_constraint("ck_email_branding_one_of_alt_text_or_text_is_null", "email_branding")
