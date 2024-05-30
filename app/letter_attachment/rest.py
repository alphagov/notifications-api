from datetime import UTC, datetime

from flask import Blueprint, jsonify, request

from app.dao.templates_dao import dao_get_template_by_id, dao_update_template
from app.errors import InvalidRequest, register_errors
from app.letter_attachment.schema import post_archive_letter_attachment_schema, post_create_letter_attachment_schema
from app.models import LetterAttachment
from app.schema_validation import validate

letter_attachment_blueprint = Blueprint("letter_attachment", __name__)
register_errors(letter_attachment_blueprint)


@letter_attachment_blueprint.route("/letter-attachment/<uuid:letter_attachment_id>", methods=["GET"])
def get_letter_attachment(letter_attachment_id):
    letter_attachment = LetterAttachment.query.get_or_404(letter_attachment_id)

    return jsonify(letter_attachment.serialize())


@letter_attachment_blueprint.route("/letter-attachment", methods=["POST"])
def create_letter_attachment():
    data = request.get_json()

    validate(data, post_create_letter_attachment_schema)

    if (template := dao_get_template_by_id(data["template_id"])) is None:
        raise InvalidRequest("template-not-found", 404)

    if template.letter_attachment:
        raise InvalidRequest("template-already-has-attachment", 400)

    letter_attachment = LetterAttachment(
        id=data["upload_id"],
        created_by_id=data["created_by_id"],
        original_filename=data["original_filename"],
        page_count=data["page_count"],
        template=template,
    )

    # need to call this function so it creates a new template history version
    dao_update_template(template)

    return jsonify(letter_attachment.serialize()), 201


@letter_attachment_blueprint.route("/letter-attachment/<uuid:letter_attachment_id>/archive", methods=["POST"])
def archive_letter_attachment(letter_attachment_id):
    data = request.get_json()

    validate(data, post_archive_letter_attachment_schema)

    letter_attachment = LetterAttachment.query.get_or_404(letter_attachment_id)
    if not (template := letter_attachment.template):
        raise InvalidRequest("letter-attachment-already-archived", 400)
    template.letter_attachment = None
    letter_attachment.archived_at = datetime.now(UTC).replace(tzinfo=None)
    letter_attachment.archived_by_id = data["archived_by"]
    dao_update_template(template)

    return "", 204
