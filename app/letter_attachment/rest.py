from flask import Blueprint

from app.errors import register_errors

letter_attachment_blueprint = Blueprint("letter_attachment", __name__)
register_errors(letter_attachment_blueprint)


@letter_attachment_blueprint.route("/letter_attachment/<uuid:letter_attachment_id>", methods=["GET"])
def get_letter_attachment_by_id(letter_attachment_id):
    pass


@letter_attachment_blueprint.route("/letter_attachment", methods=["POST"])
def create_letter_attachment():
    pass
