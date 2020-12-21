import json
import uuid
from collections import namedtuple
from datetime import datetime
from unittest.mock import Mock

import pytest

from app.clients.cbc_proxy import CBCProxyClient, CBCProxyException, CBCProxyEE, CBCProxyCanary
from app.utils import DATETIME_FORMAT


@pytest.fixture(scope='function')
def cbc_proxy_client(client, mocker):
    client = CBCProxyClient()
    current_app = mocker.Mock(config={
        'CBC_PROXY_AWS_ACCESS_KEY_ID': 'cbc-proxy-aws-access-key-id',
        'CBC_PROXY_AWS_SECRET_ACCESS_KEY': 'cbc-proxy-aws-secret-access-key',
        'CBC_PROXY_ENABLED': True,
    })
    client.init_app(current_app)
    return client


@pytest.fixture
def cbc_proxy_ee(cbc_proxy_client):
    return cbc_proxy_client.get_proxy('ee')


@pytest.fixture
def cbc_proxy_vodafone(cbc_proxy_client):
    return cbc_proxy_client.get_proxy('vodafone')


@pytest.mark.parametrize('provider_name, expected_provider_class', [
    ('ee', CBCProxyEE),
    ('canary', CBCProxyCanary),
])
def test_cbc_proxy_client_returns_correct_client(provider_name, expected_provider_class):
    mock_lambda = Mock()
    cbc_proxy_client = CBCProxyClient()
    cbc_proxy_client._lambda_client = mock_lambda

    ret = cbc_proxy_client.get_proxy(provider_name)

    assert type(ret) == expected_provider_class
    assert ret._lambda_client == mock_lambda


def test_cbc_proxy_lambda_client_has_correct_region(cbc_proxy_ee):
    assert cbc_proxy_ee._lambda_client._client_config.region_name == 'eu-west-2'


def test_cbc_proxy_lambda_client_has_correct_keys(cbc_proxy_ee):
    key = cbc_proxy_ee._lambda_client._request_signer._credentials.access_key
    secret = cbc_proxy_ee._lambda_client._request_signer._credentials.secret_key

    assert key == 'cbc-proxy-aws-access-key-id'
    assert secret == 'cbc-proxy-aws-secret-access-key'


def test_cbc_proxy_ee_create_and_send_invokes_function(mocker, cbc_proxy_ee):
    identifier = 'my-identifier'
    headline = 'my-headline'
    description = 'my-description'

    sent = 'a-passed-through-sent-value'
    expires = 'a-passed-through-expires-value'

    # a single area which is a square including london
    areas = [{
        'description': 'london',
        'polygon': [
            [51.12, -1.2],
            [51.12, 1.2],
            [51.74, 1.2],
            [51.74, -1.2],
            [51.12, -1.2],
        ],
    }]

    ld_client_mock = mocker.patch.object(
        cbc_proxy_ee,
        '_lambda_client',
        create=True,
    )

    ld_client_mock.invoke.return_value = {
        'StatusCode': 200,
    }

    cbc_proxy_ee.create_and_send_broadcast(
        identifier=identifier,
        message_number='0000007b',
        headline=headline,
        description=description,
        areas=areas,
        sent=sent, expires=expires,
    )

    ld_client_mock.invoke.assert_called_once_with(
        FunctionName='bt-ee-1-proxy',
        InvocationType='RequestResponse',
        Payload=mocker.ANY,
    )

    kwargs = ld_client_mock.invoke.mock_calls[0][-1]
    payload_bytes = kwargs['Payload']
    payload = json.loads(payload_bytes)

    assert payload['identifier'] == identifier
    assert 'message_number' not in payload
    assert payload['message_format'] == 'cap'
    assert payload['message_type'] == 'alert'
    assert payload['headline'] == headline
    assert payload['description'] == description
    assert payload['areas'] == areas
    assert payload['sent'] == sent
    assert payload['expires'] == expires


def test_cbc_proxy_ee_cancel_invokes_function(mocker, cbc_proxy_ee):
    identifier = 'my-identifier'
    MockProviderMessage = namedtuple(
        'BroadcastProviderMessage', ['id', 'message_number', 'created_at']
    )

    provider_messages = [
        MockProviderMessage(uuid.uuid4(), '0000007b', datetime(2020, 12, 16)),
        MockProviderMessage(uuid.uuid4(), '0000004e', datetime(2020, 12, 17))
    ]
    sent = '2020-12-17 14:19:44.130585'

    ld_client_mock = mocker.patch.object(
        cbc_proxy_ee,
        '_lambda_client',
        create=True,
    )

    ld_client_mock.invoke.return_value = {
        'StatusCode': 200,
    }

    cbc_proxy_ee.cancel_broadcast(
        identifier=identifier,
        message_number='00000050',
        previous_provider_messages=provider_messages,
        sent=sent
    )

    ld_client_mock.invoke.assert_called_once_with(
        FunctionName='bt-ee-1-proxy',
        InvocationType='RequestResponse',
        Payload=mocker.ANY,
    )

    kwargs = ld_client_mock.invoke.mock_calls[0][-1]
    payload_bytes = kwargs['Payload']
    payload = json.loads(payload_bytes)

    assert payload['identifier'] == identifier
    assert 'message_number' not in payload
    assert payload['message_format'] == 'cap'
    assert payload['message_type'] == 'cancel'
    assert payload['references'] == [
        {
            "message_id": str(provider_messages[0].id),
            "sent": provider_messages[0].created_at.strftime(DATETIME_FORMAT)
        },
        {
            "message_id": str(provider_messages[1].id),
            "sent": provider_messages[1].created_at.strftime(DATETIME_FORMAT)
        },
    ]
    assert payload['sent'] == sent


def test_cbc_proxy_vodafone_create_and_send_invokes_function(mocker, cbc_proxy_vodafone):
    identifier = 'my-identifier'
    headline = 'my-headline'
    description = 'my-description'

    sent = 'a-passed-through-sent-value'
    expires = 'a-passed-through-expires-value'

    # a single area which is a square including london
    areas = [{
        'description': 'london',
        'polygon': [
            [51.12, -1.2],
            [51.12, 1.2],
            [51.74, 1.2],
            [51.74, -1.2],
            [51.12, -1.2],
        ],
    }]

    ld_client_mock = mocker.patch.object(
        cbc_proxy_vodafone,
        '_lambda_client',
        create=True,
    )

    ld_client_mock.invoke.return_value = {
        'StatusCode': 200,
    }

    cbc_proxy_vodafone.create_and_send_broadcast(
        identifier=identifier,
        message_number='0000007b',
        headline=headline,
        description=description,
        areas=areas,
        sent=sent, expires=expires,
    )

    ld_client_mock.invoke.assert_called_once_with(
        FunctionName='vodafone-1-proxy',
        InvocationType='RequestResponse',
        Payload=mocker.ANY,
    )

    kwargs = ld_client_mock.invoke.mock_calls[0][-1]
    payload_bytes = kwargs['Payload']
    payload = json.loads(payload_bytes)

    assert payload['identifier'] == identifier
    assert payload['message_number'] == '0000007b'
    assert payload['message_format'] == 'ibag'
    assert payload['message_type'] == 'alert'
    assert payload['headline'] == headline
    assert payload['description'] == description
    assert payload['areas'] == areas
    assert payload['sent'] == sent
    assert payload['expires'] == expires


def test_cbc_proxy_vodafone_cancel_invokes_function(mocker, cbc_proxy_vodafone):
    identifier = 'my-identifier'
    MockProviderMessage = namedtuple(
        'BroadcastProviderMessage',
        ['id', 'message_number', 'created_at']
    )

    provider_messages = [
        MockProviderMessage(uuid.uuid4(), 78, datetime(2020, 12, 16)),
        MockProviderMessage(uuid.uuid4(), 123, datetime(2020, 12, 17))
    ]
    sent = '2020-12-18 14:19:44.130585'

    ld_client_mock = mocker.patch.object(
        cbc_proxy_vodafone,
        '_lambda_client',
        create=True,
    )

    ld_client_mock.invoke.return_value = {
        'StatusCode': 200,
    }

    cbc_proxy_vodafone.cancel_broadcast(
        identifier=identifier,
        message_number='00000050',
        previous_provider_messages=provider_messages,
        sent=sent
    )

    ld_client_mock.invoke.assert_called_once_with(
        FunctionName='vodafone-1-proxy',
        InvocationType='RequestResponse',
        Payload=mocker.ANY,
    )

    kwargs = ld_client_mock.invoke.mock_calls[0][-1]
    payload_bytes = kwargs['Payload']
    payload = json.loads(payload_bytes)

    assert payload['identifier'] == identifier
    assert payload['message_number'] == '00000050'
    assert payload['message_format'] == 'ibag'
    assert payload['message_type'] == 'cancel'
    assert payload['references'] == [
        {
            "message_id": str(provider_messages[0].id),
            "message_number": '0000004e',
            "sent": provider_messages[0].created_at.strftime(DATETIME_FORMAT)
        },
        {
            "message_id": str(provider_messages[1].id),
            "message_number": '0000007b',
            "sent": provider_messages[1].created_at.strftime(DATETIME_FORMAT)
        },
    ]
    assert payload['sent'] == sent


def test_cbc_proxy_create_and_send_handles_invoke_error(mocker, cbc_proxy_ee):
    identifier = 'my-identifier'
    headline = 'my-headline'
    description = 'my-description'

    sent = 'a-passed-through-sent-value'
    expires = 'a-passed-through-expires-value'

    # a single area which is a square including london
    areas = [{
        'description': 'london',
        'polygon': [
            [51.12, -1.2],
            [51.12, 1.2],
            [51.74, 1.2],
            [51.74, -1.2],
            [51.12, -1.2],
        ],
    }]

    ld_client_mock = mocker.patch.object(
        cbc_proxy_ee,
        '_lambda_client',
        create=True,
    )

    ld_client_mock.invoke.return_value = {
        'StatusCode': 400,
    }

    with pytest.raises(CBCProxyException) as e:
        cbc_proxy_ee.create_and_send_broadcast(
            identifier=identifier,
            message_number='0000007b',
            headline=headline,
            description=description,
            areas=areas,
            sent=sent, expires=expires,
        )

    assert e.match('Could not invoke lambda')

    ld_client_mock.invoke.assert_called_once_with(
        FunctionName='bt-ee-1-proxy',
        InvocationType='RequestResponse',
        Payload=mocker.ANY,
    )


def test_cbc_proxy_create_and_send_handles_function_error(mocker, cbc_proxy_ee):
    identifier = 'my-identifier'
    headline = 'my-headline'
    description = 'my-description'

    sent = 'a-passed-through-sent-value'
    expires = 'a-passed-through-expires-value'

    # a single area which is a square including london
    areas = [{
        'description': 'london',
        'polygon': [
            [51.12, -1.2],
            [51.12, 1.2],
            [51.74, 1.2],
            [51.74, -1.2],
            [51.12, -1.2],
        ],
    }]

    ld_client_mock = mocker.patch.object(
        cbc_proxy_ee,
        '_lambda_client',
        create=True,
    )

    ld_client_mock.invoke.return_value = {
        'StatusCode': 200,
        'FunctionError': 'something',
    }

    with pytest.raises(CBCProxyException) as e:
        cbc_proxy_ee.create_and_send_broadcast(
            identifier=identifier,
            message_number='0000007b',
            headline=headline,
            description=description,
            areas=areas,
            sent=sent, expires=expires,
        )

    assert e.match('Function exited with unhandled exception')

    ld_client_mock.invoke.assert_called_once_with(
        FunctionName='bt-ee-1-proxy',
        InvocationType='RequestResponse',
        Payload=mocker.ANY,
    )


def test_cbc_proxy_send_canary_invokes_function(mocker, cbc_proxy_client):
    identifier = str(uuid.uuid4())

    canary_client = cbc_proxy_client.get_proxy('canary')

    ld_client_mock = mocker.patch.object(
        canary_client,
        '_lambda_client',
        create=True,
    )

    ld_client_mock.invoke.return_value = {
        'StatusCode': 200,
    }

    canary_client.send_canary(
        identifier=identifier,
    )

    ld_client_mock.invoke.assert_called_once_with(
        FunctionName='canary',
        InvocationType='RequestResponse',
        Payload=mocker.ANY,
    )

    kwargs = ld_client_mock.invoke.mock_calls[0][-1]
    payload_bytes = kwargs['Payload']
    payload = json.loads(payload_bytes)

    assert payload['identifier'] == identifier


def test_cbc_proxy_ee_send_link_test_invokes_function(mocker, cbc_proxy_ee):
    identifier = str(uuid.uuid4())

    ld_client_mock = mocker.patch.object(
        cbc_proxy_ee,
        '_lambda_client',
        create=True,
    )

    ld_client_mock.invoke.return_value = {
        'StatusCode': 200,
    }

    cbc_proxy_ee.send_link_test(
        identifier=identifier,
        sequential_number='0000007b',
    )

    ld_client_mock.invoke.assert_called_once_with(
        FunctionName='bt-ee-1-proxy',
        InvocationType='RequestResponse',
        Payload=mocker.ANY,
    )

    kwargs = ld_client_mock.invoke.mock_calls[0][-1]
    payload_bytes = kwargs['Payload']
    payload = json.loads(payload_bytes)

    assert payload['identifier'] == identifier
    assert payload['message_type'] == 'test'
    assert 'message_number' not in payload
    assert payload['message_format'] == 'cap'


def test_cbc_proxy_vodafone_send_link_test_invokes_function(mocker, cbc_proxy_vodafone):
    identifier = str(uuid.uuid4())

    ld_client_mock = mocker.patch.object(
        cbc_proxy_vodafone,
        '_lambda_client',
        create=True,
    )

    ld_client_mock.invoke.return_value = {
        'StatusCode': 200,
    }

    cbc_proxy_vodafone.send_link_test(
        identifier=identifier,
        sequential_number='0000007b',
    )

    ld_client_mock.invoke.assert_called_once_with(
        FunctionName='vodafone-1-proxy',
        InvocationType='RequestResponse',
        Payload=mocker.ANY,
    )

    kwargs = ld_client_mock.invoke.mock_calls[0][-1]
    payload_bytes = kwargs['Payload']
    payload = json.loads(payload_bytes)

    assert payload['identifier'] == identifier
    assert payload['message_type'] == 'test'
    assert payload['message_number'] == '0000007b'
    assert payload['message_format'] == 'ibag'
