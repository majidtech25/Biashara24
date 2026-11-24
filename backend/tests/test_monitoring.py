"""Error reporting stays off unless SENTRY_DSN is set, and never sends personal data."""
import sentry_sdk

from app import monitoring
from app.config import get_settings


def _setup(monkeypatch, dsn):
    calls = []
    # Record the settings instead of starting a real Sentry client (no network in tests).
    monkeypatch.setattr(sentry_sdk, "init", lambda **options: calls.append(options))
    if dsn:
        monkeypatch.setenv("SENTRY_DSN", dsn)
    else:
        monkeypatch.delenv("SENTRY_DSN", raising=False)
    get_settings.cache_clear()
    try:
        return monitoring.setup(), calls
    finally:
        get_settings.cache_clear()


def test_error_reporting_is_off_without_a_dsn(monkeypatch):
    enabled, calls = _setup(monkeypatch, "")
    assert enabled is False and calls == []


def test_error_reporting_turns_on_with_a_dsn(monkeypatch):
    enabled, calls = _setup(monkeypatch, "https://public@example.invalid/1")
    assert enabled is True and len(calls) == 1
    options = calls[0]
    assert options["dsn"] == "https://public@example.invalid/1"
    assert options["send_default_pii"] is False
    assert options["max_request_body_size"] == "never"
    assert options["include_local_variables"] is False
    assert options["traces_sample_rate"] == 0
