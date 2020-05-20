"""

Revision ID: 0322_update_postage_constraint_2
Revises: 0321_update_postage_constraint_1
Create Date: 2020-05-12 16:20:16.548347

"""
from alembic import op


revision = '0322_update_postage_constraint_2'
down_revision = '0321_update_postage_constraint_1'


def upgrade():
    op.drop_constraint('chk_templates_postage', 'templates')
    op.drop_constraint('chk_templates_history_postage', 'templates_history')

    op.execute("""
        ALTER TABLE templates ADD CONSTRAINT "chk_templates_postage"
        CHECK (
            CASE WHEN template_type = 'letter' THEN
                postage is not null and postage in ('first', 'second', 'europe', 'rest-of-world')
            ELSE
                postage is null
            END
        )
        NOT VALID
    """)
    op.execute("""
        ALTER TABLE templates_history ADD CONSTRAINT "chk_templates_history_postage"
        CHECK (
            CASE WHEN template_type = 'letter' THEN
                postage is not null and postage in ('first', 'second', 'europe', 'rest-of-world')
            ELSE
                postage is null
            END
        )
        NOT VALID
    """)
    op.execute('COMMIT')


def downgrade():
    pass
