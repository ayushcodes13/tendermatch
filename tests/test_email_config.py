"""Verify that the documented email environment contract is read as expected."""

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EMAIL_SETTINGS = ("SENDER_EMAIL", "SENDER_PASSWORD", "RECEIVER_EMAIL")
READ_SETTINGS = """import config, json
print(json.dumps([config.SENDER_EMAIL, config.SENDER_PASSWORD, config.RECEIVER_EMAIL]))
"""


def load_email_settings(tmp_path, supplied):
    env = os.environ.copy()
    for name in EMAIL_SETTINGS:
        env.pop(name, None)
    env.update(supplied)
    env["PYTHONPATH"] = str(ROOT)
    env["PYTHON_DOTENV_DISABLED"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", READ_SETTINGS],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_config_reads_the_documented_email_environment_names(tmp_path):
    assert load_email_settings(tmp_path, {
        "SENDER_EMAIL": "sender@example.test",
        "SENDER_PASSWORD": "test-smtp-password",
        "RECEIVER_EMAIL": "recipient@example.test",
    }) == ["sender@example.test", "test-smtp-password", "recipient@example.test"]


def test_config_keeps_missing_email_settings_unset(tmp_path):
    assert load_email_settings(tmp_path, {}) == [None, None, None]
