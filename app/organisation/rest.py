from flask import abort, Blueprint, jsonify, request, current_app
from sqlalchemy.exc import IntegrityError

from app.config import QueueNames
from app.dao.organisation_dao import (
    dao_create_organisation,
    dao_get_organisations,
    dao_get_organisation_by_id,
    dao_get_organisation_by_email_address,
    dao_get_organisation_services,
    dao_update_organisation,
    dao_add_service_to_organisation,
    dao_get_users_for_organisation,
    dao_add_user_to_organisation
)
from app.dao.templates_dao import dao_get_template_by_id
from app.dao.services_dao import dao_fetch_service_by_id
from app.errors import register_errors, InvalidRequest
from app.models import Organisation, KEY_TYPE_NORMAL
from app.notifications.process_notifications import persist_notification, send_notification_to_queue
from app.organisation.organisation_schema import (
    post_create_organisation_schema,
    post_update_organisation_schema,
    post_link_service_to_organisation_schema,
)
from app.schema_validation import validate

organisation_blueprint = Blueprint('organisation', __name__)
register_errors(organisation_blueprint)


@organisation_blueprint.errorhandler(IntegrityError)
def handle_integrity_error(exc):
    """
    Handle integrity errors caused by the unique constraint on ix_organisation_name
    """
    if 'ix_organisation_name' in str(exc):
        return jsonify(result="error",
                       message="Organisation name already exists"), 400
    if 'duplicate key value violates unique constraint "domain_pkey"' in str(exc):
        return jsonify(result='error',
                       message='Domain already exists'), 400

    current_app.logger.exception(exc)
    return jsonify(result='error', message="Internal server error"), 500


@organisation_blueprint.route('', methods=['GET'])
def get_organisations():
    organisations = [
        org.serialize_for_list() for org in dao_get_organisations()
    ]

    return jsonify(organisations)


@organisation_blueprint.route('/<uuid:organisation_id>', methods=['GET'])
def get_organisation_by_id(organisation_id):
    organisation = dao_get_organisation_by_id(organisation_id)
    return jsonify(organisation.serialize())


@organisation_blueprint.route('/by-domain', methods=['GET'])
def get_organisation_by_domain():

    domain = request.args.get('domain')

    if not domain or '@' in domain:
        abort(400)

    organisation = dao_get_organisation_by_email_address(
        'example@{}'.format(request.args.get('domain'))
    )

    if not organisation:
        abort(404)

    return jsonify(organisation.serialize())


@organisation_blueprint.route('', methods=['POST'])
def create_organisation():
    data = request.get_json()

    validate(data, post_create_organisation_schema)

    organisation = Organisation(**data)
    dao_create_organisation(organisation)
    return jsonify(organisation.serialize()), 201


@organisation_blueprint.route('/<uuid:organisation_id>', methods=['POST'])
def update_organisation(organisation_id):
    data = request.get_json()
    validate(data, post_update_organisation_schema)
    result = dao_update_organisation(organisation_id, **data)

    if data.get('agreement_signed') is True:
        # if a platform admin has manually adjusted the organisation, don't tell people
        if data.get('agreement_signed_by_id'):
            send_notifications_on_mou_signed(organisation_id)

    if result:
        return '', 204
    else:
        raise InvalidRequest("Organisation not found", 404)


@organisation_blueprint.route('/<uuid:organisation_id>/service', methods=['POST'])
def link_service_to_organisation(organisation_id):
    data = request.get_json()
    validate(data, post_link_service_to_organisation_schema)
    service = dao_fetch_service_by_id(data['service_id'])
    service.organisation = None

    dao_add_service_to_organisation(service, organisation_id)

    return '', 204


@organisation_blueprint.route('/<uuid:organisation_id>/services', methods=['GET'])
def get_organisation_services(organisation_id):
    services = dao_get_organisation_services(organisation_id)
    sorted_services = sorted(services, key=lambda s: (-s.active, s.name))
    return jsonify([s.serialize_for_org_dashboard() for s in sorted_services])


@organisation_blueprint.route('/<uuid:organisation_id>/services-with-usage', methods=['GET'])
def get_organisation_services_usage(organisation_id):
    services = dao_get_organisation_services(organisation_id)
    sorted_services = sorted(services, key=lambda s: (-s.active, s.name))
    return jsonify([s.serialize_for_org_dashboard() for s in sorted_services])


@organisation_blueprint.route('/<uuid:organisation_id>/users/<uuid:user_id>', methods=['POST'])
def add_user_to_organisation(organisation_id, user_id):
    new_org_user = dao_add_user_to_organisation(organisation_id, user_id)
    return jsonify(data=new_org_user.serialize())


@organisation_blueprint.route('/<uuid:organisation_id>/users', methods=['GET'])
def get_organisation_users(organisation_id):
    org_users = dao_get_users_for_organisation(organisation_id)
    return jsonify(data=[x.serialize() for x in org_users])


@organisation_blueprint.route('/unique', methods=["GET"])
def is_organisation_name_unique():
    organisation_id, name = check_request_args(request)

    name_exists = Organisation.query.filter(Organisation.name.ilike(name)).first()

    result = (not name_exists) or str(name_exists.id) == organisation_id
    return jsonify(result=result), 200


def check_request_args(request):
    org_id = request.args.get('org_id')
    name = request.args.get('name', None)
    errors = []
    if not org_id:
        errors.append({'org_id': ["Can't be empty"]})
    if not name:
        errors.append({'name': ["Can't be empty"]})
    if errors:
        raise InvalidRequest(errors, status_code=400)
    return org_id, name


def send_notifications_on_mou_signed(organisation_id):
    organisation = dao_get_organisation_by_id(organisation_id)
    notify_service = dao_fetch_service_by_id(current_app.config['NOTIFY_SERVICE_ID'])

    def _send_notification(template_id, recipient, personalisation):
        template = dao_get_template_by_id(template_id)

        saved_notification = persist_notification(
            template_id=template.id,
            template_version=template.version,
            recipient=recipient,
            service=notify_service,
            personalisation=personalisation,
            notification_type=template.template_type,
            api_key_id=None,
            key_type=KEY_TYPE_NORMAL,
            reply_to_text=notify_service.get_default_reply_to_email_address()
        )
        send_notification_to_queue(saved_notification, research_mode=False, queue=QueueNames.NOTIFY)

    personalisation = {
        'mou_link': '{}/agreement/{}.pdf'.format(
            current_app.config['ADMIN_BASE_URL'],
            'crown' if organisation.crown else 'non-crown'
        ),
        'org_name': organisation.name,
        'org_dashboard_link': '{}/organisations/{}'.format(
            current_app.config['ADMIN_BASE_URL'],
            organisation.id
        ),
        'signed_by_name': organisation.agreement_signed_by.name,
        'on_behalf_of_name': organisation.agreement_signed_on_behalf_of_name
    }

    # let notify team know something's happened
    _send_notification(
        current_app.config['MOU_NOTIFY_TEAM_ALERT_TEMPLATE_ID'],
        'notify-support+{}@digital.cabinet-office.gov.uk'.format(current_app.config['NOTIFY_ENVIRONMENT']),
        personalisation
    )

    if not organisation.agreement_signed_on_behalf_of_email_address:
        signer_template_id = 'MOU_SIGNER_RECEIPT_TEMPLATE_ID'
    else:
        signer_template_id = 'MOU_SIGNED_ON_BEHALF_SIGNER_RECEIPT_TEMPLATE_ID'

        # let the person who has been signed on behalf of know.
        _send_notification(
            current_app.config['MOU_SIGNED_ON_BEHALF_ON_BEHALF_RECEIPT_TEMPLATE_ID'],
            organisation.agreement_signed_on_behalf_of_email_address,
            personalisation
        )

    # let the person who signed know - the template is different depending on if they signed on behalf of someone
    _send_notification(
        current_app.config[signer_template_id],
        organisation.agreement_signed_by.email_address,
        personalisation
    )
