import json

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


def test_cbc_proxy_ld_client_has_correct_region(cbc_proxy):
    assert cbc_proxy._ld_client._client_config.region_name == 'eu-west-2'
    pass


def test_cbc_proxy_ld_client_has_correct_keys(cbc_proxy):
    key = cbc_proxy._ld_client._request_signer._credentials.access_key
    secret = cbc_proxy._ld_client._request_signer._credentials.secret_key

    assert key == 'cbc-proxy-aws-access-key-id'
    assert secret == 'cbc-proxy-aws-secret-access-key'


def test_cbc_proxy_create_and_send_invokes_function(mocker, cbc_proxy):
    identifier = 'my-identifier'
    headline = 'my-headline'
    description = 'my-description'

    ld_client_mock = mocker.patch.object(
        cbc_proxy,
        '_ld_client',
        create=True,
    )

    cbc_proxy.create_and_send_broadcast(
        identifier=identifier,
        headline=headline,
        description=description,
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
    assert payload['headline'] == headline
    assert payload['description'] == description
