"""empty message

Revision ID: 0057_change_email_template
Revises: 0056_minor_updates
Create Date: 2016-10-11 09:24:45.669018

"""

# revision identifiers, used by Alembic.
from datetime import datetime

revision = '0057_change_email_template'
down_revision = '0056_minor_updates'

from alembic import op
user_id= '6af522d0-2915-4e52-83a3-3690455a5fe6'
service_id = 'd6aa2c68-a2d9-4437-ab19-3ae8eb202553'
template_id = 'eb4d9930-87ab-4aef-9bce-786762687884'


def upgrade():
    template_history_insert = """INSERT INTO templates_history (id, name, template_type, created_at,
                                                                content, archived, service_id,
                                                                subject, created_by_id, version)
                                 VALUES ('{}', '{}', '{}', '{}', '{}', False, '{}', '{}', '{}', 1)
                              """
    template_insert = """INSERT INTO templates (id, name, template_type, created_at,
                                                content, archived, service_id, subject, created_by_id, version)
                                 VALUES ('{}', '{}', '{}', '{}', '{}', False, '{}', '{}', '{}', 1)
                              """
    template_content = \
        """Hi ((name)),\n\nClick this link to confirm your new email address:
        \n\n((url))
        \n\nIf you didn’t try to change the email address for your GOV.​UK Notify account, let us know here:
        \n\n((feedback_url))"""

    template_name = 'Confirm new email address'
    op.execute(template_history_insert.format(template_id,
                                              template_name,
                                              'email',
                                              datetime.utcnow(), template_content,
                                              service_id,
                                              template_name, user_id))
    op.execute(template_insert.format(template_id,
                                      template_name,
                                      'email',
                                      datetime.utcnow(),
                                      template_content,
                                      service_id,
                                      template_name, user_id))


def downgrade():
   op.execute("delete from templates_history where id = '{}'".format(template_id))
   op.execute("delete from templates where id = '{}'".format(template_id))
