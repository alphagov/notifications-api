import os
import uuid
from app import db
from app import models
from app.history_meta import create_history


def load_example_csv(file):
    file_path = os.path.join("test_csv_files", "{}.csv".format(file))
    with open(file_path) as f:
        return f.read()


def add_user_to_service(service, user):
    service.users.append(user)
    db.session.add(service)
    db.session.commit()


def create_model(cls_name, create_uuid=False, **kwargs):
    obj = getattr(models, cls_name)(**kwargs)
    if create_uuid:
        obj.id = uuid.uuid4()
    db.session.add(obj)
    db.session.commit()
    return obj


def create_history_from_model(obj, version=1):
    old_version = obj.version
    history_obj = create_history(obj)
    history_obj.version = version
    db.session.add(history_obj)
    db.session.commit()
    # Revert the version to the original version
    obj.version = old_version
    return history_obj
