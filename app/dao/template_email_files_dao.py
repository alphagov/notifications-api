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

