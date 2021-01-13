"""

Revision ID: 0336_broadcast_msg_content_2
Revises: 0335_broadcast_msg_content
Create Date: 2020-12-04 15:06:22.544803

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm.session import Session

from app.models import BroadcastMessage

revision = '0336_broadcast_msg_content_2'
down_revision = '0335_broadcast_msg_content'


def upgrade():
    session = Session(bind=op.get_bind())

    broadcast_messages = session.query(BroadcastMessage).filter(BroadcastMessage.content == None)

    for broadcast_message in broadcast_messages:
        broadcast_message.content = broadcast_message.template._as_utils_template_with_personalisation(
            broadcast_message.personalisation
        ).content_with_placeholders_filled_in

    session.commit()

    op.alter_column('broadcast_message', 'content', nullable=False)


def downgrade():
    op.alter_column('broadcast_message', 'content', nullable=True)
