import datetime
from collections import defaultdict

from app import db
from app.dao.dao_utils import VersionOptions, autocommit, version_class
from app.models import Template, TemplateEmailFile, TemplateEmailFileHistory, TemplateHistory


@autocommit
@version_class(VersionOptions(TemplateEmailFile, history_class=TemplateEmailFileHistory))
def dao_create_template_email_files(template_email_file: TemplateEmailFile):
    template = Template.query.get(template_email_file.template_id)
    template_email_file.template_version = template.version
    db.session.add(template_email_file)


@autocommit
def dao_get_template_email_files_by_template_id(template_id, template_version=None):
    if template_version is not None:
        template_email_files_all_template_versions = TemplateEmailFileHistory.query.filter(
            TemplateEmailFileHistory.template_id == template_id,
            TemplateEmailFileHistory.template_version <= template_version,
        ).order_by(TemplateEmailFileHistory.template_version.desc())

        email_files_grouped_by_id = defaultdict(list)
        for file in template_email_files_all_template_versions:
            email_files_grouped_by_id[file.id].append(file)

        return [
            max(email_file_versions, key=lambda x: x.template_version)
            for _, email_file_versions in email_files_grouped_by_id.items()
        ]
    return TemplateEmailFile.query.filter(TemplateEmailFile.template_id == template_id).all()


@autocommit
def dao_get_template_email_file_by_id(template_email_files_id, template_version=None):
    if template_version is not None:
        return (
            TemplateEmailFileHistory.query.filter(
                TemplateEmailFileHistory.id == template_email_files_id,
                TemplateEmailFileHistory.template_version <= template_version,
            )
            .order_by(TemplateEmailFileHistory.template_version.desc())
            .first()
        )

    return TemplateEmailFile.query.get(template_email_files_id)

