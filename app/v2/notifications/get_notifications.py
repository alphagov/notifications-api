from io import BytesIO

from flask import current_app, jsonify, request, send_file, url_for

from app import api_user, authenticated_service
from app.constants import (
    LETTER_TYPE,
    NOTIFICATION_PENDING_VIRUS_CHECK,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_VIRUS_SCAN_FAILED,
)
from app.dao import notifications_dao
from app.letters.utils import get_letter_pdf_and_metadata
from app.schema_validation import validate
from app.v2.errors.errors import BadRequestError, PDFNotReadyError
from app.v2.notifications import v2_notification_blueprint
from app.v2.notifications.notification_schemas import (
    get_notifications_request,
    notification_by_id,
)


@v2_notification_blueprint.route("/<notification_id>", methods=["GET"])
def get_notification_by_id(notification_id):
    _data = {"notification_id": notification_id}
    validate(_data, notification_by_id)
    notification = notifications_dao.get_notification_with_personalisation(
        authenticated_service.id, notification_id, key_type=None
    )
    return jsonify(notification.serialize_with_cost_data()), 200


@v2_notification_blueprint.route("/<notification_id>/pdf", methods=["GET"])
def get_pdf_for_notification(notification_id):
    _data = {"notification_id": notification_id}
    validate(_data, notification_by_id)
    notification = notifications_dao.get_notification_by_id(notification_id, authenticated_service.id, _raise=True)

    if notification.notification_type != LETTER_TYPE:
        raise BadRequestError(message="Notification is not a letter")

    if notification.status == NOTIFICATION_VIRUS_SCAN_FAILED:
        raise BadRequestError(message="File did not pass the virus scan")

    if notification.status == NOTIFICATION_TECHNICAL_FAILURE:
        raise BadRequestError(message=f"PDF not available for letters in status {notification.status}")

    if notification.status == NOTIFICATION_PENDING_VIRUS_CHECK:
        raise PDFNotReadyError

    try:
        pdf_data, metadata = get_letter_pdf_and_metadata(notification)
    except Exception as e:
        raise PDFNotReadyError from e

    return send_file(path_or_file=BytesIO(pdf_data), mimetype="application/pdf")


@v2_notification_blueprint.route("", methods=["GET"])
def get_notifications():
    _data = request.args.to_dict(flat=False)

    # flat=False makes everything a list, but we only ever allow one value for "older_than"
    if "older_than" in _data:
        _data["older_than"] = _data["older_than"][0]

    # and client reference
    if "reference" in _data:
        _data["reference"] = _data["reference"][0]

    if "include_jobs" in _data:
        _data["include_jobs"] = _data["include_jobs"][0]

    data = validate(_data, get_notifications_request)

    paginated_notifications = notifications_dao.get_notifications_for_service(
        str(authenticated_service.id),
        filter_dict=data,
        key_type=api_user.key_type,
        with_template=True,
        older_than=data.get("older_than"),
        client_reference=data.get("reference"),
        page_size=current_app.config.get("API_PAGE_SIZE"),
        include_jobs=data.get("include_jobs"),
        count_pages=False,
    )

    def _build_links(notifications):
        _links = {
            "current": url_for(".get_notifications", _external=True, **data),
        }

        if len(notifications):
            next_query_params = dict(data, older_than=notifications[-1].id)
            _links["next"] = url_for(".get_notifications", _external=True, **next_query_params)

        return _links

    return (
        jsonify(
            notifications=[notification.serialize_with_cost_data() for notification in paginated_notifications.items],
            links=_build_links(paginated_notifications.items),
        ),
        200,
    )
