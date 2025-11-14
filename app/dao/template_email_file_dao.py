from app.dao.dao_utils import autocommit
from app.models import TemplateEmailFile, TemplateEmailFileHistory


@autocommit
def dao_get_template_email_file_by_id(template_email_files_id, template_version=None):
    if template_version is not None:
        return (
            TemplateEmailFileHistory.query.filter_by(
                TemplateEmailFileHistory.id == template_email_files_id,
                TemplateEmailFileHistory.template_version <= template_version,
            )
            .order_by(TemplateEmailFileHistory.template_version.desc())
            .first()
        )

    return TemplateEmailFile.query.get(template_email_files_id)
