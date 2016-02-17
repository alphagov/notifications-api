from flask import (
    Blueprint,
    jsonify,
    current_app
)

from sqlalchemy.exc import DataError
from sqlalchemy.orm.exc import NoResultFound

from app.dao.templates_dao import get_model_templates
from app.schemas import (template_schema, templates_schema)

template = Blueprint('template', __name__)


# I am going to keep these for admin like operations
# Permissions should restrict who can access this endpoint
# TODO auth to be added.
@template.route('/<int:template_id>', methods=['GET'])
@template.route('', methods=['GET'])
def get_template(template_id=None):
    try:
        templates = get_model_templates(template_id=template_id)
    except DataError:
        return jsonify(result="error", message="Invalid template id"), 400
    except NoResultFound:
        return jsonify(result="error", message="Template not found"), 404
    except Exception as e:
        current_app.logger.exception(e)
        return jsonify(result="error", message=str(e)), 500
    if isinstance(templates, list):
        data, errors = templates_schema.dump(templates)
    else:
        data, errors = template_schema.dump(templates)
    if errors:
        return jsonify(result="error", message=str(errors))
    return jsonify(data=data)
