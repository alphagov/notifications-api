import datetime
from collections import defaultdict

from app import db
from app.dao.dao_utils import VersionOptions, autocommit, version_class
from app.models import Template, TemplateEmailFile, TemplateEmailFileHistory, TemplateHistory


@autocommit
@version_class(
    VersionOptions(TemplateEmailFile, history_class=TemplateEmailFileHistory),
    VersionOptions(Template, history_class=TemplateHistory),
)
def dao_create_template_email_file(template_email_file: TemplateEmailFile):
    template = Template.query.get(template_email_file.template_id)
    template.updated_at = datetime.datetime.utcnow()
    template_email_file.template_version = template.version + 1
    db.session.add(template_email_file)


@autocommit
def dao_get_template_email_files_by_template_id(template_id, template_version=None):
    if template_version:
        template_email_files_all_template_versions = TemplateEmailFileHistory.query.filter(
            TemplateEmailFileHistory.template_id == template_id,
            TemplateEmailFileHistory.template_version <= template_version,
        )
        email_files_grouped_by_id = defaultdict(list)
        for file in template_email_files_all_template_versions:
            email_files_grouped_by_id[file.id].append(file)

        return list(
            filter(
                lambda x: not x.archived_at,
                [
                    max(email_file_versions, key=lambda x: x.template_version)
                    for _, email_file_versions in email_files_grouped_by_id.items()
                ],
            )
        )

    return TemplateEmailFile.query.filter(
        TemplateEmailFile.template_id == template_id,
        TemplateEmailFile.archived_at.is_(None),
    ).all()


@autocommit
def dao_get_template_email_file_by_id(template_email_file_id):
    return TemplateEmailFile.query.filter(TemplateEmailFile.id == template_email_file_id).one()


@autocommit
@version_class(
    VersionOptions(TemplateEmailFile, history_class=TemplateEmailFileHistory),
    VersionOptions(Template, history_class=TemplateHistory),
)
def dao_update_template_email_file(template_email_file: TemplateEmailFile):
    template = Template.query.get(template_email_file.template_id)
    template.updated_at = datetime.datetime.utcnow()
    template_email_file.template_version = template.version + 1
    db.session.add(template_email_file)
    db.session.add(template)
