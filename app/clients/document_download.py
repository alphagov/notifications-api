import base64

import requests


class DocumentDownloadClient:

    def init_app(self, app):
        self.api_host = app.config['DOCUMENT_DOWNLOAD_API_HOST']
        self.auth_token = app.config['DOCUMENT_DOWNLOAD_API_KEY']

    def get_upload_url(self, service_id):
        return "{}/services/{}/documents".format(self.api_host, service_id)

    def upload_document(self, service_id, file_contents):
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

        return response.json()['document']['url']
