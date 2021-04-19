from app import db
from app.dao.dao_utils import autocommit
from app.models import TemplateFolder


def dao_get_template_folder_by_id_and_service_id(template_folder_id, service_id):
    return TemplateFolder.query.filter(
        TemplateFolder.id == template_folder_id,
        TemplateFolder.service_id == service_id
    ).one()


def dao_get_valid_template_folders_by_id(folder_ids):
    return TemplateFolder.query.filter(TemplateFolder.id.in_(folder_ids)).all()


@autocommit
def dao_create_template_folder(template_folder):
    db.session.add(template_folder)


@autocommit
def dao_update_template_folder(template_folder):
    db.session.add(template_folder)


@autocommit
def dao_delete_template_folder(template_folder):
    db.session.delete(template_folder)
