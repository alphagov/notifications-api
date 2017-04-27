import json


def test_dvla_callback_should_not_need_auth(client):
    data = json.dumps({"somekey": "somevalue"})
    response = client.post(
        path='/notifications/letter/dvla',
        data=data,
        headers=[('Content-Type', 'application/json')])

    assert response.status_code == 200
