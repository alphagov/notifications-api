from sqlalchemy import desc

from app import db
from app.dao.dao_utils import autocommit
from app.errors import InvalidRequest
from app.exceptions import ArchiveValidationError
from app.models import ServiceEmailReplyTo


def dao_get_reply_to_by_service_id(service_id):
    reply_to = db.session.query(
        ServiceEmailReplyTo
    ).filter(
        ServiceEmailReplyTo.service_id == service_id,
        ServiceEmailReplyTo.archived == False  # noqa
    ).order_by(desc(ServiceEmailReplyTo.is_default), desc(ServiceEmailReplyTo.created_at)).all()
    return reply_to


def dao_get_reply_to_by_id(service_id, reply_to_id):
    reply_to = db.session.query(
        ServiceEmailReplyTo
    ).filter(
        ServiceEmailReplyTo.service_id == service_id,
        ServiceEmailReplyTo.id == reply_to_id,
        ServiceEmailReplyTo.archived == False  # noqa
    ).order_by(ServiceEmailReplyTo.created_at).one()
    return reply_to


@autocommit
def add_reply_to_email_address_for_service(service_id, email_address, is_default):
    old_default = _get_existing_default(service_id)
    if is_default:
        _reset_old_default_to_false(old_default)
    else:
        _raise_when_no_default(old_default)

    new_reply_to = ServiceEmailReplyTo(service_id=service_id, email_address=email_address, is_default=is_default)
    db.session.add(new_reply_to)
    return new_reply_to


@autocommit
def update_reply_to_email_address(service_id, reply_to_id, email_address, is_default):
    old_default = _get_existing_default(service_id)
    if is_default:
        _reset_old_default_to_false(old_default)
    else:
        if old_default.id == reply_to_id:
            raise InvalidRequest("You must have at least one reply to email address as the default.", 400)

    reply_to_update = ServiceEmailReplyTo.query.get(reply_to_id)
    reply_to_update.email_address = email_address
    reply_to_update.is_default = is_default
    db.session.add(reply_to_update)
    return reply_to_update


@autocommit
def archive_reply_to_email_address(service_id, reply_to_id):
    reply_to_archive = ServiceEmailReplyTo.query.filter_by(
        id=reply_to_id,
        service_id=service_id
    ).one()

    if reply_to_archive.is_default:
        raise ArchiveValidationError("You cannot delete a default email reply to address")

    reply_to_archive.archived = True

    db.session.add(reply_to_archive)
    return reply_to_archive


def _get_existing_default(service_id):
    existing_reply_to = dao_get_reply_to_by_service_id(service_id=service_id)
    if existing_reply_to:
        old_default = [x for x in existing_reply_to if x.is_default]
        if len(old_default) == 1:
            return old_default[0]
        else:
            raise Exception(
                "There should only be one default reply to email for each service. Service {} has {}".format(
                    service_id, len(old_default)))
    return None


def _reset_old_default_to_false(old_default):
    if old_default:
        old_default.is_default = False
        db.session.add(old_default)


def _raise_when_no_default(old_default):
    # check that the update is not updating the only default to false
    if not old_default:
        raise InvalidRequest("You must have at least one reply to email address as the default.", 400)
