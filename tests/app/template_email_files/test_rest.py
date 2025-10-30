import uuid
import json
from tests import create_admin_authorization_header
import datetime

def test_create_email_files_post(client, sample_service, sample_email_template):
    data = {
        "id": "d963f496-b075-4e13-90ae-1f009feddbc5",
        "filename": "example.pdf",
        "link_text": "click this link!",
        "retention_period": 90,
        "validate_users_email": True,
        "template_id": str(sample_email_template.id),
        "template_version": int(sample_email_template.version),
        "created_by_id" : str(sample_service.users[0].id),}
    data = json.dumps(data)
    auth_header = create_admin_authorization_header()
    response = client.post(f"/service/{sample_service.id}/{sample_email_template.id}/template_email_files",headers = [("Content-Type", "application/json"), auth_header], data = data)
    assert response.status_code == 201
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp.get("data").get("filename") == "example.pdf"