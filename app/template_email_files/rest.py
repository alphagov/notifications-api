from flask import Blueprint

template_email_files_blueprint = Blueprint(
    "template_email_files", __name__, url_prefix="/service/<uuid:service_id>/<uuid:template_id>/template_email_files"
)

@template_email_files_blueprint.route("", methods=["POST"])
def create_template(service_id, template_id):
    pass