from app import celery
from app.dao.services_dao import get_model_services


@celery.task(name="refresh-services")
def refresh_services():
    print(get_model_services())
    for service in get_model_services():
        celery.control.add_consumer(str(service.id))
