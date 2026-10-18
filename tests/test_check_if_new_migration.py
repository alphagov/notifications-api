import os
import subprocess
import sys
from pathlib import Path

import pytest
import requests

from scripts import check_if_new_migration

PROJECT_ROOT = Path(check_if_new_migration.__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "error",
    [
        requests.exceptions.ConnectionError,
        requests.exceptions.MissingSchema,
        requests.exceptions.InvalidURL,
        requests.exceptions.TooManyRedirects,
        requests.exceptions.Timeout,
    ],
)
def test_get_current_db_version_handles_request_failures(error, mocker, monkeypatch, capsys):
    monkeypatch.setenv("API_HOST_NAME", "https://api.example.test")
    mocker.patch.object(check_if_new_migration.requests, "get", side_effect=error)

    assert check_if_new_migration.get_current_db_version() == ""
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Could not make web request to https://api.example.test/_status\n"


@pytest.mark.parametrize(
    "status_code, body",
    [(503, b"Service unavailable"), (200, b"not json"), (200, b"{}")],
)
def test_get_current_db_version_keeps_response_diagnostics(status_code, body, mocker, capsys):
    response = requests.Response()
    response.status_code = status_code
    response._content = body
    mocker.patch.object(check_if_new_migration.requests, "get", return_value=response)

    assert check_if_new_migration.get_current_db_version() == ""
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"code {status_code}" in captured.err
    assert f'response "{body.decode()}"' in captured.err


def test_get_current_db_version_reads_status_response(mocker):
    response = requests.Response()
    response.status_code = 200
    response._content = b'{"db_version": "0123_latest"}'
    mocker.patch.object(check_if_new_migration.requests, "get", return_value=response)

    assert check_if_new_migration.get_current_db_version() == "0123_latest"


@pytest.mark.parametrize(
    "current_version, expected_output",
    [("0123_latest", "no\n"), ("0122_previous", "yes\n"), ("", "yes\n")],
)
def test_run_reports_whether_migrations_are_needed(current_version, expected_output, mocker, capsys):
    mocker.patch.object(check_if_new_migration, "get_current_db_version", return_value=current_version)
    mocker.patch.object(check_if_new_migration, "get_latest_db_migration_to_apply", return_value="0123_latest")

    check_if_new_migration.run()

    assert capsys.readouterr().out == expected_output


@pytest.mark.parametrize("api_host_name", [None, "api.example.test"])
def test_script_requests_migrations_when_status_url_has_no_scheme(api_host_name):
    environment = os.environ.copy()
    if api_host_name is None:
        environment.pop("API_HOST_NAME", None)
    else:
        environment["API_HOST_NAME"] = api_host_name

    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts/check_if_new_migration.py")],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == "yes\n"
    assert "Could not make web request" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    "script, expected_output, succeeds",
    [("print('yes')", "yes\n", True), ("print('no')", "no\n", True), ("raise SystemExit(7)", "", False)],
)
def test_make_target_preserves_script_output_and_failure(script, expected_output, succeeds, tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/check_if_new_migration.py").write_text(script)

    result = subprocess.run(
        ["make", "--silent", "-f", str(PROJECT_ROOT / "Makefile"), "check-if-migrations-to-run"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert (result.returncode == 0) == succeeds
    assert result.stdout == expected_output
