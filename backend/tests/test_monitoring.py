"""Error reporting stays off unless SENTRY_DSN is set."""
import sentry_sdk

from app import monitoring
from app.config import get_settings


def test_error_reporting_is_off_without_a_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    get_settings.cache_clear()
    try:
        assert monitoring.setup() is False
        assert not sentry_sdk.get_client().is_active()
    finally:
        get_settings.cache_clear()


def test_error_reporting_turns_on_with_a_dsn(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://public@o0.ingest.sentry.io/1")
    get_settings.cache_clear()
    try:
        assert monitoring.setup() is True
        client = sentry_sdk.get_client()
        assert client.is_active() and client.options["send_default_pii"] is False
        assert client.options["max_request_body_size"] == "never" and client.options["include_local_variables"] is False
    finally:
        sentry_sdk.init()  # no DSN: turns reporting off again for the other tests
        get_settings.cache_clear()
