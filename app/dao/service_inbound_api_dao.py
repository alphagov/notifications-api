from app import db
from app.authentication.utils import generate_secret
from app.dao.dao_utils import transactional


@transactional
def save_service_inbound_api(service_inbound_api):

    service_inbound_api.bearer_token = generate_secret(service_inbound_api.bearer_token)
    db.session.add(service_inbound_api)
