import requests
from flask import current_app, request
from flask.ctx import has_request_context


class DocumentDownloadError(Exception):
    def __init__(self, message, status_code):
        self.message = message
        self.status_code = status_code

    @classmethod
    def from_exception(cls, e):
        message = e.response.json()["error"]
        status_code = e.response.status_code
        return cls(message, status_code)


class DocumentDownloadClient:
    def __init__(self, app):
        self.api_host_external = app.config["DOCUMENT_DOWNLOAD_API_HOST"]
        self.api_host_internal = app.config["DOCUMENT_DOWNLOAD_API_HOST_INTERNAL"]
        self.auth_token = app.config["DOCUMENT_DOWNLOAD_API_KEY"]
        self.requests_session = requests.Session()

    def get_upload_url_for_simulated_email(self, service_id):
        """
        This is the URL displayed in the API response for emails sent to a simulated email address.
        """
        return f"{self.api_host_external}/services/{service_id}/documents"

    def _get_upload_url(self, service_id):
        """
        When uploading a document we use the internal route to document-download-api. This internal URL
        can only be accessed from other apps, so should not be displayed to users.
        """
        return f"{self.api_host_internal}/services/{service_id}/documents"

    def upload_document(
        self,
        service_id,
        file_contents,
        is_csv=None,
        confirmation_email: str | None = None,
        retention_period: str | None = None,
        filename: str | None = None,
    ):
        try:
            data = {
                "document": file_contents,
                "is_csv": is_csv or False,
            }

            if confirmation_email:
                data["confirmation_email"] = confirmation_email

            if retention_period:
                data["retention_period"] = retention_period

            if filename:
                data["filename"] = filename

            headers = {"Authorization": f"Bearer {self.auth_token}"}
            if has_request_context() and hasattr(request, "get_onwards_request_headers"):
                headers.update(request.get_onwards_request_headers())

            response = self.requests_session.post(
                self._get_upload_url(service_id),
                headers=headers,
                json=data,
            )

            response.raise_for_status()
        except requests.RequestException as e:
            # if doc dl responds with a non-400, (eg 403) it's referring to credentials that the API and Doc DL use.
            # we don't want to tell users about that, so anything that isn't a 400 (virus scan failed or file type
            # unrecognised) should be raised as a 500 internal server error here.
            if e.response is None:
                raise Exception(f"Unhandled document download error: {repr(e)}") from e
            elif e.response.status_code == 400:
                error = DocumentDownloadError.from_exception(e)
                current_app.logger.info("Document download request failed with error: %s", error.message)
                raise error from e
            else:
                raise Exception(f"Unhandled document download error: {e.response.text}") from e

        return response.json()["document"]["url"]
