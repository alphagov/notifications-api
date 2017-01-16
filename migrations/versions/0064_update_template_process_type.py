"""empty message

Revision ID: 0064_update_template_process_type
Revises: 0063_templates_process_type
Create Date: 2017-01-16 11:08:00.520678

"""

# revision identifiers, used by Alembic.
revision = '0064_update_template_process'
down_revision = '0063_templates_process_type'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.execute("Update templates set process_type = 'normal'")
    op.execute("Update templates_history set process_type = 'normal'")
    op.alter_column('templates', 'process_type',
                    existing_type=sa.VARCHAR(length=255),
                    nullable=False)
    op.alter_column('templates_history', 'process_type',
                    existing_type=sa.VARCHAR(length=255),
                    nullable=False)


def downgrade():
    op.alter_column('templates_history', 'process_type',
                    existing_type=sa.VARCHAR(length=255),
                    nullable=True)
    op.alter_column('templates', 'process_type',
                    existing_type=sa.VARCHAR(length=255),
                    nullable=True)
