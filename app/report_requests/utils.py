from sqlalchemy import case, func, text
from sqlalchemy.orm import aliased

from app import db
from app.aws.s3 import stream_to_s3
from app.models import (
    Job,
    Notification,
    Template,
    User,
)

EMAIL_STATUS_FORMATTED = {
    "created": "Sending",
    "sending": "Sending",
    "delivered": "Delivered",
    "pending": "Sending",
    "failed": "Failed",
    "technical-failure": "Tech issue",
    "temporary-failure": "Content or inbox issue",
    "permanent-failure": "No such address",
    "pending-virus-check": "Sending",
    "virus-scan-failed": "Attachment has virus",
    "validation-failed": "Content or inbox issue",
}

SMS_STATUS_FORMATTED = {
    "created": "Sending",
    "sending": "Sending",
    "pending": "Sending",
    "sent": "Sent",
    "delivered": "Delivered",
    "failed": "Failed",
    "technical-failure": "Tech issue",
    "temporary-failure": "Carrier issue",
    "permanent-failure": "No such number",
}

FR_TRANSLATIONS = {
    "Recipient": "Destinataire",
    "Template": "Gabarit",
    "Type": "Type",
    "Sent by": "Envoyé par",
    "Sent by email": "Envoyé par courriel",
    "Job": "Tâche",
    "Row number": "Numéro de ligne",
    "Status": "État",
    "Sent Time": "Heure d’envoi",
    # notification types
    "email": "courriel",
    "sms": "sms",
    # notification statuses
    "Failed": "Échec",
    "Tech issue": "Problème technique",
    "Content or inbox issue": "Problème de contenu ou de boîte de réception",
    "Attachment has virus": "La pièce jointe contient un virus",
    "Delivered": "Livraison réussie",
    "In transit": "Envoi en cours",
    "Exceeds Protected A": "Niveau supérieur à Protégé A",
    "Carrier issue": "Problème du fournisseur",
    "No such number": "Numéro inexistant",
    "Sent": "Envoyé",
    "Blocked": "Message bloqué",
    "No such address": "Adresse inexistante",
    # "Can't send to this international number": "" # no translation exists for this yet
}


class Translate:
    def __init__(self, language="en"):
        """Initialize the Translate class with a language."""
        self.language = language
        self.translations = {
            "fr": FR_TRANSLATIONS,
        }

    def translate(self, x):
        """Translate the given string based on the set language."""
        if self.language == "fr" and x in self.translations["fr"]:
            return self.translations["fr"][x]
        return x


def build_notifications_query(
    service_id, notification_type, language, notification_statuses=None, job_id=None, days_limit=7
):
    if notification_statuses is None:
        notification_statuses = []
    # Create aliases for the tables to make the query more readable
    n = aliased(Notification)
    t = aliased(Template)
    j = aliased(Job)
    u = aliased(User)

    # Build the inner subquery (returns enum values, cast as text for notification_type)
    query_filters = [
        n.service_id == service_id,
        n.notification_type == notification_type,
        n.created_at > func.now() - text(f"interval '{days_limit} days'"),
    ]

    if notification_statuses:
        statuses = Notification.substitute_status(notification_statuses)
        query_filters.append(n.status.in_(statuses))

    if job_id:
        query_filters.append(n.job_id == job_id)

    inner_query = (
        db.session.query(
            n.to.label("to"),
            t.name.label("template_name"),
            n.notification_type.cast(db.String).label("notification_type"),
            u.name.label("user_name"),
            u.email_address.label("user_email"),
            j.original_file_name.label("job_name"),
            n.job_row_number.label("job_row_number"),
            n.status.label("status"),
            n.created_at.label("created_at"),
        )
        .join(t, t.id == n.template_id)
        .outerjoin(j, j.id == n.job_id)
        .outerjoin(u, u.id == n.created_by_id)
        .filter(*query_filters)
        .subquery()
    )

    # Map statuses for translation
    translate = Translate(language).translate

    email_status_cases = [(inner_query.c.status == k, translate(v)) for k, v in EMAIL_STATUS_FORMATTED.items()]
    sms_status_cases = [(inner_query.c.status == k, translate(v)) for k, v in SMS_STATUS_FORMATTED.items()]

    if notification_type == "email":
        status_expr = case(*email_status_cases, else_=inner_query.c.status)
    elif notification_type == "sms":
        status_expr = case(*sms_status_cases, else_=inner_query.c.status)
    else:
        status_expr = inner_query.c.status

    if language == "fr":
        status_expr = func.coalesce(func.nullif(status_expr, ""), "").label(translate("Status"))
    else:
        status_expr = status_expr.label(translate("Status"))

    notification_type_translated = case(
        (inner_query.c.notification_type == "email", translate("email")),
        (inner_query.c.notification_type == "sms", translate("sms")),
        else_=inner_query.c.notification_type,
    ).label(translate("Type"))

    query_columns = [
        inner_query.c.to.label(translate("Recipient")),
        inner_query.c.template_name.label(translate("Template")),
        notification_type_translated,
    ]

    if job_id is None:
        query_columns.extend(
            [
                func.coalesce(inner_query.c.user_name, "").label(translate("Sent by")),
                func.coalesce(inner_query.c.user_email, "").label(translate("Sent by email")),
            ]
        )
    else:
        query_columns.insert(0, (inner_query.c.job_row_number + 1).label(translate("Row number")))

    query_columns.extend(
        [
            func.coalesce(inner_query.c.job_name, "").label(translate("Job")),
            status_expr,
            func.to_char(
                func.timezone("America/Toronto", func.timezone("UTC", inner_query.c.created_at)),
                "YYYY-MM-DD HH24:MI:SS",
            ).label(translate("Sent Time")),
        ]
    )

    return db.session.query(*query_columns).order_by(
        inner_query.c.created_at.asc() if job_id else inner_query.c.created_at.desc()
    )


def compile_query_for_copy(query):
    compiled_query = query.statement.compile(dialect=db.engine.dialect, compile_kwargs={"literal_binds": True})
    return f"COPY ({compiled_query}) TO STDOUT WITH CSV HEADER"


def stream_query_to_s3(copy_command, s3_bucket, s3_key):
    conn = db.engine.raw_connection()
    try:
        cursor = conn.cursor()
        stream_to_s3(
            bucket_name=s3_bucket,
            object_key=s3_key,
            copy_command=copy_command,
            cursor=cursor,
        )
    finally:
        conn.close()
