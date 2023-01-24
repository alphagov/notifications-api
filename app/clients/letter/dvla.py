import boto3


class SSMParameter:
    def __init__(self, key, ssm_client):
        self.key = key
        self.ssm_client = ssm_client

    def get(self):
        return self.ssm_client.get_parameter(Name=self.key, WithDecryption=True)["Parameter"]["Value"]

    def set(self, value):
        # this errors if the parameter doesn't exist yet in SSM as we haven't supplied a `Type`
        # this is fine for our purposes, as we'll always want to pre-seed this data.
        self.ssm_client.put_parameter(Name=self.key, Value=value, Overwrite=True)


class DVLAClient:
    """
    DVLA HTTP API letter client.
    """

    statsd_client = None

    def init_app(self, region, statsd_client):
        ssm_client = boto3.client("ssm", region_name=region)
        self.dvla_username = SSMParameter(key="/notify/api/dvla_username", ssm_client=ssm_client)
        self.dvla_password = SSMParameter(key="/notify/api/dvla_password", ssm_client=ssm_client)
        self.dvla_api_key = SSMParameter(key="/notify/api/dvla_api_key", ssm_client=ssm_client)

        self.statsd_client = statsd_client

    @property
    def name(self):
        return "dvla"

    def send_letter(self):
        pass
