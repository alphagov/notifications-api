from flask import jsonify

from app.v2.govuk_alerts import v2_govuk_alerts_blueprint


@v2_govuk_alerts_blueprint.route('')
def get_broadcasts():
    return jsonify({})
