import json

import boto3

# The variable names in this file have specific meaning in a CAP message
#
# identifier is a unique field for each CAP message
#
# headline is a field which we are not sure if we will use
#
# description is the body of the message

# areas is a list of dicts, with the following items
# * description is a string which populates the areaDesc field
# * polygon is a list of lat/long pairs
#
# references is a whitespace separated list of message identifiers
# where each identifier is a previous sent message
# ie a Cancel message would have a unique identifier but have the identifier of
#    the preceeding Alert message in the references field


# Noop = no operation
class CBCProxyNoopClient:

    def init_app(self, app):
        pass

    def send_canary(
        self,
        identifier,
    ):
        pass

    def create_and_send_broadcast(
        self,
        identifier, headline, description, areas
    ):
        pass

    # We have not implementated updating a broadcast
    def update_and_send_broadcast(
        self,
        identifier, references, headline, description, areas
    ):
        pass

    # We have not implemented cancelling a broadcast
    def cancel_broadcast(
        self,
        identifier, references, headline, description, areas
    ):
        pass


class CBCProxyClient:

    def init_app(self, app):
        self._lambda_client = boto3.client(
            'lambda',
            region_name='eu-west-2',
            aws_access_key_id=app.config['CBC_PROXY_AWS_ACCESS_KEY_ID'],
            aws_secret_access_key=app.config['CBC_PROXY_AWS_SECRET_ACCESS_KEY'],
        )

    def send_canary(
        self,
        identifier,
    ):
        payload_bytes = bytes(json.dumps({
            'identifier': identifier,
        }), encoding='utf8')

        result = self._lambda_client.invoke(
            FunctionName='canary',
            InvocationType='RequestResponse',
            Payload=payload_bytes,
        )

        if result['StatusCode'] > 299:
            raise Exception('Could not invoke lambda')

        if 'FunctionError' in result:
            raise Exception('Function exited with unhandled exception')

    def create_and_send_broadcast(
        self,
        identifier, headline, description, areas,
    ):
        payload_bytes = bytes(json.dumps({
            'identifier': identifier,
            'headline': headline,
            'description': description,
            'areas': areas,
        }), encoding='utf8')

        result = self._lambda_client.invoke(
            FunctionName='bt-ee-1-proxy',
            InvocationType='RequestResponse',
            Payload=payload_bytes,
        )

        if result['StatusCode'] > 299:
            raise Exception('Could not invoke lambda')

        if 'FunctionError' in result:
            raise Exception('Function exited with unhandled exception')

    # We have not implementated updating a broadcast
    def update_and_send_broadcast(
        self,
        identifier, references, headline, description, areas,
    ):
        pass

    # We have not implemented cancelling a broadcast
    def cancel_broadcast(
        self,
        identifier, references, headline, description, areas,
    ):
        pass
