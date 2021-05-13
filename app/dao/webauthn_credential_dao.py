from app import db
from app.dao.dao_utils import autocommit
from app.models import WebauthnCredential


def dao_get_webauthn_credential_by_user_and_id(user_id, webauthn_credential_id):
    return WebauthnCredential.query.filter(
        WebauthnCredential.user_id == user_id,
        WebauthnCredential.id == webauthn_credential_id
    ).one()


@autocommit
def dao_create_webauthn_credential(
    *,
    user_id,
    name,
    credential_data,
    registration_response,
):
    webauthn_credential = WebauthnCredential(
        user_id=user_id,
        name=name,
        credential_data=credential_data,
        registration_response=registration_response
    )
    db.session.add(webauthn_credential)
    return webauthn_credential


@autocommit
def dao_update_webauthn_credential_name(webauthn_credential, new_name):
    webauthn_credential.name = new_name
    db.session.add(webauthn_credential)
    return webauthn_credential


@autocommit
def dao_delete_webauthn_credential(webauthn_credential):
    db.session.delete(webauthn_credential)
