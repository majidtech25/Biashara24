"""Logging and optional error reporting.

Logs go to standard output with a timestamp, where `docker compose logs` collects them.
When SENTRY_DSN is set, unhandled errors are also sent to Sentry. Request bodies,
cookies, user details and local variables are not sent, and no performance tracing
is collected.
"""
import logging

from .config import get_settings


def setup():
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    if not settings.sentry_dsn:
        return False
    import sentry_sdk
    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment,
                    send_default_pii=False, max_request_body_size="never",
                    include_local_variables=False, traces_sample_rate=0)
    logging.getLogger("biashara360").info("Error reporting to Sentry is on")
    return True
