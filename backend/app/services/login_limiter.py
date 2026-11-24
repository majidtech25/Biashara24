"""Slow down password guessing: too many failed sign-ins lock that email from that address.

Counts live in this server process's memory. They reset when the server restarts and
are not shared between several server processes; put a reverse-proxy limit in front
as well when running more than one process.
"""
import time
from collections import defaultdict, deque
from threading import Lock

MAX_FAILURES = 5
WINDOW_SECONDS = 15 * 60

_failures: dict[tuple[str, str], deque] = defaultdict(deque)
_lock = Lock()


def _key(ip: str | None, username: str) -> tuple[str, str]:
    return (ip or "unknown", username.strip().lower())


def _prune(entries: deque, now: float) -> None:
    while entries and now - entries[0] >= WINDOW_SECONDS:
        entries.popleft()


def retry_after(ip: str | None, username: str) -> int:
    """Seconds until another attempt is allowed, or 0 if allowed now."""
    now = time.monotonic()
    with _lock:
        entries = _failures.get(_key(ip, username))
        if not entries:
            return 0
        _prune(entries, now)
        if len(entries) < MAX_FAILURES:
            return 0
        return max(1, int(WINDOW_SECONDS - (now - entries[0])) + 1)


def record_failure(ip: str | None, username: str) -> None:
    now = time.monotonic()
    with _lock:
        entries = _failures[_key(ip, username)]
        _prune(entries, now)
        entries.append(now)


def record_success(ip: str | None, username: str) -> None:
    with _lock:
        _failures.pop(_key(ip, username), None)


def reset() -> None:
    with _lock:
        _failures.clear()
