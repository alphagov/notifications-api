import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "process_sender_names.py"


def _run_script(csv_text: str) -> str:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=csv_text,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_skips_public_bodies_and_ingests_commercial_ids():
    output = _run_script(
        "Sender ID,MEF Approved,Date Approved,Merchant\n"
        "MonzoAlert,approved,2026-01-01,Monzo\n"
        "GOVuk,approved,2026-01-01,Cabinet Office\n"
        "HMRCC,approved,2026-01-01,HMRC\n"
        "NHS app,approved,2026-01-01,NHS\n"
    )

    assert "INSERT INTO protected_sender_ids VALUES ('monzoalert') ON CONFLICT DO NOTHING;" in output
    assert "govuk" not in output
    assert "hmrcc" not in output


def test_lowercases_and_strips_whitespace():
    output = _run_script("Sender ID,Merchant\n  HS Bank  ,Monzo\n")

    assert "VALUES ('hsbank')" in output
