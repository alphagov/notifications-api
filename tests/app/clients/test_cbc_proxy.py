import json
import uuid

import pytest

from app.clients.cbc_proxy import CBCProxyClient


@pytest.fixture(scope='function')
def cbc_proxy(client, mocker):
    client = CBCProxyClient()
    current_app = mocker.Mock(config={
        'CBC_PROXY_AWS_ACCESS_KEY_ID': 'cbc-proxy-aws-access-key-id',
        'CBC_PROXY_AWS_SECRET_ACCESS_KEY': 'cbc-proxy-aws-secret-access-key',
    })
    client.init_app(current_app)
    return client


def test_cbc_proxy_lambda_client_has_correct_region(cbc_proxy):
    assert cbc_proxy._lambda_client._client_config.region_name == 'eu-west-2'


def test_cbc_proxy_lambda_client_has_correct_keys(cbc_proxy):
    key = cbc_proxy._lambda_client._request_signer._credentials.access_key
    secret = cbc_proxy._lambda_client._request_signer._credentials.secret_key

    assert key == 'cbc-proxy-aws-access-key-id'
    assert secret == 'cbc-proxy-aws-secret-access-key'


def test_cbc_proxy_create_and_send_invokes_function(mocker, cbc_proxy):
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
        cbc_proxy,
        '_lambda_client',
        create=True,
    )

    ld_client_mock.invoke.return_value = {
        'StatusCode': 200,
    }

    cbc_proxy.create_and_send_broadcast(
        identifier=identifier,
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
    assert payload['message_type'] == 'alert'
    assert payload['headline'] == headline
    assert payload['description'] == description
    assert payload['areas'] == areas
    assert payload['sent'] == sent
    assert payload['expires'] == expires


def test_cbc_proxy_create_and_send_handles_invoke_error(mocker, cbc_proxy):
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
        cbc_proxy,
        '_lambda_client',
        create=True,
    )

    ld_client_mock.invoke.return_value = {
        'StatusCode': 400,
    }

    with pytest.raises(Exception) as e:
        cbc_proxy.create_and_send_broadcast(
            identifier=identifier,
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


def test_cbc_proxy_create_and_send_handles_function_error(mocker, cbc_proxy):
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
        cbc_proxy,
        '_lambda_client',
        create=True,
    )

    ld_client_mock.invoke.return_value = {
        'StatusCode': 200,
        'FunctionError': 'something',
    }

    with pytest.raises(Exception) as e:
        cbc_proxy.create_and_send_broadcast(
            identifier=identifier,
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


def test_cbc_proxy_send_canary_invokes_function(mocker, cbc_proxy):
    identifier = str(uuid.uuid4())

    ld_client_mock = mocker.patch.object(
        cbc_proxy,
        '_lambda_client',
        create=True,
    )

    ld_client_mock.invoke.return_value = {
        'StatusCode': 200,
    }

    cbc_proxy.send_canary(
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


def test_cbc_proxy_send_canary_handles_invoke_error(mocker, cbc_proxy):
    identifier = str(uuid.uuid4())

    ld_client_mock = mocker.patch.object(
        cbc_proxy,
        '_lambda_client',
        create=True,
    )

    ld_client_mock.invoke.return_value = {
        'StatusCode': 400,
    }

    with pytest.raises(Exception) as e:
        cbc_proxy.send_canary(
            identifier=identifier,
        )

        assert e.match('Function exited with unhandled exception')

    ld_client_mock.invoke.assert_called_once_with(
        FunctionName='canary',
        InvocationType='RequestResponse',
        Payload=mocker.ANY,
    )


def test_cbc_proxy_send_canary_handles_function_error(mocker, cbc_proxy):
    identifier = str(uuid.uuid4())

    ld_client_mock = mocker.patch.object(
        cbc_proxy,
        '_lambda_client',
        create=True,
    )

    ld_client_mock.invoke.return_value = {
        'StatusCode': 200,
        'FunctionError': 'something',
    }

    with pytest.raises(Exception) as e:
        cbc_proxy.send_canary(
            identifier=identifier,
        )

        assert e.match('Could not invoke lambda')

    ld_client_mock.invoke.assert_called_once_with(
        FunctionName='canary',
        InvocationType='RequestResponse',
        Payload=mocker.ANY,
    )


def test_cbc_proxy_send_link_test_invokes_function(mocker, cbc_proxy):
    identifier = str(uuid.uuid4())

    ld_client_mock = mocker.patch.object(
        cbc_proxy,
        '_lambda_client',
        create=True,
    )

    ld_client_mock.invoke.return_value = {
        'StatusCode': 200,
    }

    cbc_proxy.send_link_test(
        identifier=identifier,
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


def test_cbc_proxy_send_link_test_handles_invoke_error(mocker, cbc_proxy):
    identifier = str(uuid.uuid4())

    ld_client_mock = mocker.patch.object(
        cbc_proxy,
        '_lambda_client',
        create=True,
    )

    ld_client_mock.invoke.return_value = {
        'StatusCode': 400,
    }

    with pytest.raises(Exception) as e:
        cbc_proxy.send_link_test(
            identifier=identifier,
        )

        assert e.match('Function exited with unhandled exception')

    ld_client_mock.invoke.assert_called_once_with(
        FunctionName='bt-ee-1-proxy',
        InvocationType='RequestResponse',
        Payload=mocker.ANY,
    )


def test_cbc_proxy_send_link_test_handles_function_error(mocker, cbc_proxy):
    identifier = str(uuid.uuid4())

    ld_client_mock = mocker.patch.object(
        cbc_proxy,
        '_lambda_client',
        create=True,
    )

    ld_client_mock.invoke.return_value = {
        'StatusCode': 200,
        'FunctionError': 'something',
    }

    with pytest.raises(Exception) as e:
        cbc_proxy.send_link_test(
            identifier=identifier,
        )

        assert e.match('Could not invoke lambda')

    ld_client_mock.invoke.assert_called_once_with(
        FunctionName='bt-ee-1-proxy',
        InvocationType='RequestResponse',
        Payload=mocker.ANY,
    )
