"""
Create Date: 2026-11-06 15:52:53.918548
"""

from alembic import op
import sqlalchemy as sa

revision = '0590_add_mailbox_template_type'
down_revision = '0589_add_mailbox_noti_type'


def upgrade():
    op.execute("ALTER TYPE template_type ADD VALUE 'mailbox'")


def downgrade():
    """
    Not suitable for production, designed for a feature branch only
    """
    enum_name = "template_type"
    tmp_name = "tmp_" + enum_name

    original_values = ("sms", "email", "letter", "broadcast")
    original_type = sa.Enum(*original_values, name=enum_name)

    op.execute("DELETE FROM templates WHERE template_type = 'mailbox'")
    op.execute("DELETE FROM templates_history WHERE template_type = 'mailbox'")

    op.execute("ALTER TABLE templates DROP CONSTRAINT ck_templates_letter_attachments")
    op.execute("ALTER TABLE templates_history DROP CONSTRAINT ck_templates_history_letter_attachments")
    op.execute("ALTER TABLE templates DROP CONSTRAINT ck_templates_non_email_has_unsubscribe_false")
    op.execute("ALTER TABLE templates_history DROP CONSTRAINT ck_templates_history_non_email_has_unsubscribe_false")
    op.execute("ALTER TABLE templates DROP CONSTRAINT chk_templates_letter_languages")
    op.execute("ALTER TABLE templates_history DROP CONSTRAINT chk_templates_history_letter_languages")


    op.execute(f"ALTER TYPE {enum_name} RENAME TO {tmp_name}")
    original_type.create(op.get_bind())

    op.execute(f"ALTER TABLE templates ALTER COLUMN template_type TYPE {enum_name} USING template_type::text::{enum_name}")
    op.execute(f"ALTER TABLE templates_history ALTER COLUMN template_type TYPE {enum_name} USING template_type::text::{enum_name}")
    op.execute(f"ALTER TABLE service_contact_list ALTER COLUMN template_type TYPE {enum_name} USING template_type::text::{enum_name}")


    op.create_check_constraint(
        "ck_templates_letter_attachments", "templates", "template_type = 'letter' OR letter_attachment_id IS NULL"
    )
    op.create_check_constraint(
        "ck_templates_history_letter_attachments",
        "templates_history",
        "template_type = 'letter' OR letter_attachment_id IS NULL",
    )
    op.create_check_constraint(
        "ck_templates_non_email_has_unsubscribe_false",
        "templates",
        "template_type = 'email' OR has_unsubscribe_link IS false",
    )
    op.create_check_constraint(
        "ck_templates_history_non_email_has_unsubscribe_false",
        "templates_history",
        "template_type = 'email' OR has_unsubscribe_link IS false",
    )
    op.execute(
        """
        ALTER TABLE templates ADD CONSTRAINT "chk_templates_letter_languages"
        CHECK (
            CASE WHEN template_type = 'letter' THEN
                letter_languages is not null
            ELSE
                letter_languages is null
            END
        )
        """
    )
    op.execute(
        """
        ALTER TABLE templates_history ADD CONSTRAINT "chk_templates_history_letter_languages"
        CHECK (
            CASE WHEN template_type = 'letter' THEN
                letter_languages is not null
            ELSE
                letter_languages is null
            END
        )
        """
    )

    op.execute(f"DROP TYPE {tmp_name}")
