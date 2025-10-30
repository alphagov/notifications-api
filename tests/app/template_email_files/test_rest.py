import json

from app.models import TemplateEmailFile
from tests import create_admin_authorization_header


def test_create_email_files_post(client, sample_service, sample_email_template):
    data = {
        "id": "d963f496-b075-4e13-90ae-1f009feddbc6",
        "filename": "example.pdf",
        "link_text": "click this link!",
        "retention_period": 90,
        "validate_users_email": True,
        "template_id": str(sample_email_template.id),
        "template_version": int(sample_email_template.version),
        "created_by_id": int(sample_service.users[0].id),
    }
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()
    response = client.post(
        f"/service/{sample_service.id}/{sample_email_template.id}/template_email_files",
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    assert response.status_code == 201
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp['data']['id'] == 'd963f496-b075-4e13-90ae-1f009feddbc6'
    assert json_resp['data']['filename'] == "example.pdf"
    assert json_resp['data']['retention_period'] == 90
    assert json_resp['data']['link_text'] == "click this link!"
    assert json_resp['data']['validate_users_email']
    assert json_resp['data']['template_id'] == str(sample_email_template.id)
    assert json_resp['data']['template_version'] == int(sample_email_template.version)
    assert json_resp['data']['created_by_id'] == str(sample_service.users[0].id)
    template_email_file = TemplateEmailFile.query.get("d963f496-b075-4e13-90ae-1f009feddbc6")
    assert template_email_file.filename == "example.pdf"
