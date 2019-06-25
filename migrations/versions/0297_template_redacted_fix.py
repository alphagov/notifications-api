"""

Revision ID: 0297_template_redacted_fix
Revises: 0296_agreement_signed_by_person
Create Date: 2019-06-25 17:02:14.350064

"""
from alembic import op


revision = '0297_template_redacted_fix'
down_revision = '0296_agreement_signed_by_person'


def upgrade():
    op.execute("""
        INSERT INTO template_redacted (template_id, redact_personalisation, updated_at, updated_by_id)
        SELECT templates.id, FALSE, now(), templates.created_by_id
        FROM templates
        WHERE templates.id NOT IN (SELECT template_id FROM template_redacted WHERE template_id = templates.id)
        ;
    """)

    op.execute("""
        create or replace function insert_redacted()
            returns trigger AS
        $$
        BEGIN
            INSERT INTO template_redacted (template_id, redact_personalisation, updated_at, updated_by_id)
            SELECT templates.id, FALSE, now(), templates.created_by_id
            FROM templates
            WHERE templates.id NOT IN (SELECT template_id FROM template_redacted WHERE template_id = templates.id);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER insert_template_redacted AFTER INSERT ON templates
        FOR EACH ROW
        EXECUTE PROCEDURE insert_redacted();
    """)


def downgrade():
    op.execute("""
        drop trigger insert_template_redacted ON templates
    """)

    op.execute("""
        drop function insert_redacted();
    """)
