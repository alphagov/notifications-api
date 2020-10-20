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
    pass


def test_cbc_proxy_lambda_client_has_correct_keys(cbc_proxy):
    key = cbc_proxy._lambda_client._request_signer._credentials.access_key
    secret = cbc_proxy._lambda_client._request_signer._credentials.secret_key

    assert key == 'cbc-proxy-aws-access-key-id'
    assert secret == 'cbc-proxy-aws-secret-access-key'
