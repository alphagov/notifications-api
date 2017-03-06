from flask import json


def test_receive_notification_returns_received_to_mmg(client):
    data = {"ID": "1234",
            "MSISDN": "447700900855",
            "Message": "Some message to notify",
            "Trigger": "Trigger?",
            "Number": "40604",
            "Channel": "SMS",
            "DateReceived": "2012-06-27-12:33:00"
            }
    response = client.post(path='/notifications/sms/receive/mmg',
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json')])

    assert response.status_code == 200
    assert response.get_data(as_text=True) == 'RECEIVED'
