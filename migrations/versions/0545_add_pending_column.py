"""

Create Date: 2025-02-10 17:07:41.828494
Revision ID: 0544_email_file_retention_fix
Revises: 0543_letter_rates_from_5_01_26

"""

revision = "0545_add_pending_column"
down_revision = "0544_email_file_retention_fix"


from alembic import op
from sqlalchemy import text


def upgrade():
    conn = op.get_bind()
    conn.execute(text("ALTER TABLE template_email_files ADD COLUMN pending boolean"))
    conn.execute(text("ALTER TABLE template_email_files_history ADD COLUMN pending boolean"))
    conn.execute(text("""
                    ALTER TABLE 
                        template_email_files 
                    ALTER COLUMN 
                        pending 
                    SET DEFAULT 
                      false
                    """))
    conn.execute(text("""
                    ALTER TABLE 
                        template_email_files_history 
                    ALTER COLUMN 
                        pending 
                    SET DEFAULT 
                      false
                    """))
    conn.execute(text("UPDATE template_email_files SET pending = false"))
    conn.execute(text("UPDATE template_email_files_history SET pending = false"))


def downgrade():
    conn = op.get_bind()
    conn.execute("ALTER TABLE template_email_files DROP COLUMN pending")
    conn.execute("ALTER TABLE template_email_files_history DROP COLUMN pending")
