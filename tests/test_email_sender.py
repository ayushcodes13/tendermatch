import sys
from types import ModuleType


if "dotenv" not in sys.modules:
    try:
        import dotenv  # noqa: F401
    except ImportError:
        dotenv_stub = ModuleType("dotenv")
        dotenv_stub.load_dotenv = lambda: None
        sys.modules["dotenv"] = dotenv_stub

import pytest

import digest.sender as sender


def test_send_email_uses_shared_sender_settings_and_tls(monkeypatch):
    calls = []

    class FakeSMTP:
        def starttls(self):
            calls.append(("starttls",))

        def login(self, username, password):
            calls.append(("login", username, password))

        def sendmail(self, from_address, to_address, message):
            calls.append(("sendmail", from_address, to_address, message))

        def quit(self):
            calls.append(("quit",))

    monkeypatch.setattr(sender, "SENDER_EMAIL", "sender@example.com")
    monkeypatch.setattr(sender, "SENDER_PASSWORD", "smtp-app-password")
    monkeypatch.setattr(
        sender.smtplib,
        "SMTP",
        lambda host, port, timeout: FakeSMTP() if timeout == 30 else None,
    )

    sender.send_email("Digest", "Tender report", "recipient@example.com")

    assert calls[0] == ("starttls",)
    assert calls[1] == ("login", "sender@example.com", "smtp-app-password")
    assert calls[2][0:3] == ("sendmail", "sender@example.com", "recipient@example.com")
    assert "Subject: Digest" in calls[2][3]
    assert calls[-1] == ("quit",)


def test_send_email_rejects_missing_shared_sender_settings(monkeypatch):
    monkeypatch.setattr(sender, "SENDER_EMAIL", None)
    monkeypatch.setattr(sender, "SENDER_PASSWORD", None)

    with pytest.raises(ValueError, match="SENDER_EMAIL or SENDER_PASSWORD"):
        sender.send_email("Digest", "Tender report", "recipient@example.com")


def test_send_email_redacts_smtp_exception_text_from_logs_and_raised_error(
    monkeypatch, capsys
):
    secret = "smtp-response-secret-value"

    class FakeSMTP:
        def starttls(self):
            raise RuntimeError(f"server echoed credential: {secret}")

        def quit(self):
            pass

    monkeypatch.setattr(sender, "SENDER_EMAIL", "sender@example.com")
    monkeypatch.setattr(sender, "SENDER_PASSWORD", "test-password")
    monkeypatch.setattr(sender.smtplib, "SMTP", lambda *args, **kwargs: FakeSMTP())

    with pytest.raises(sender.EmailDeliveryError) as raised:
        sender.send_email("Digest", "Tender report", "recipient@example.com")

    output = capsys.readouterr().out
    assert "Email failed (RuntimeError)" in output
    assert "RuntimeError" in str(raised.value)
    assert secret not in output
    assert secret not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
