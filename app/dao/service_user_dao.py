
from app import db
from app.dao.dao_utils import transactional
from app.models import ServiceUser


def dao_get_service_user(user_id, service_id):
    return ServiceUser.query.filter_by(user_id=user_id, service_id=service_id).one()


@transactional
def dao_update_service_user(service_user):
    db.session.add(service_user)
