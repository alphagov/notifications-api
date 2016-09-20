from sqlalchemy import or_

from app import db
from app.models import ServiceWhitelist

def dao_fetch_service_whitelist(service_id):
    return ServiceWhitelist.query().filter(ServiceWhitelist.service_id == service_id).all()


def dao_add_whitelisted_contact(obj):
    db.session.add(obj)
