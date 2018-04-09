import base64

import requests

from flask import current_app


class DocumentDownloadError(Exception):
    def __init__(self, message, status_code):
        self.message = message
        self.status_code = status_code

    @classmethod
    def from_exception(cls, e):
        try:
            message = e.response.json()['error']
            status_code = e.response.status_code
        except (TypeError, ValueError, AttributeError, KeyError):
            message = 'connection error'
            status_code = 503

        return cls(message, status_code)


class DocumentDownloadClient:

    def init_app(self, app):
        self.api_host = app.config['DOCUMENT_DOWNLOAD_API_HOST']
        self.auth_token = app.config['DOCUMENT_DOWNLOAD_API_KEY']

    def get_upload_url(self, service_id):
        return "{}/services/{}/documents".format(self.api_host, service_id)

    def upload_document(self, service_id, file_contents):
        try:
            response = requests.post(
                self.get_upload_url(service_id),
                headers={
                    'Authorization': "Bearer {}".format(self.auth_token),
                },
                files={
                    'document': base64.b64decode(file_contents)
                }
            )

            response.raise_for_status()
        except requests.RequestException as e:
            error = DocumentDownloadError.from_exception(e)
            current_app.logger.warning(
                'Document download request failed with error: {}'.format(error.message)
            )

            raise error

        return response.json()['document']['url']
