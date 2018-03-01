"""

Revision ID: 0172_deprioritise_examples
Revises: 0171_add_org_invite_template
Create Date: 2018-02-28 17:09:56.619803

"""
from alembic import op
from app.models import NORMAL
import sqlalchemy as sa


revision = '0172_deprioritise_examples'
down_revision = '0171_add_org_invite_template'


def upgrade():
    op.get_bind()
    op.execute("""
        update templates
        set process_type = '{}'
        where templates.id in (
            select templates.id from templates
            join templates_history on templates.id=templates_history.id
            where templates_history.name = 'Example text message template'
        )
    """.format(NORMAL))


def downgrade():
    pass
