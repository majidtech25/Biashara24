#!/usr/bin/env python3
"""Biashara360 print program for one branch.

Runs on any always-on computer on the branch's local network (Windows, Linux or a Raspberry Pi)
with Python 3.9 or newer. It needs no other packages.

Every few seconds it asks the server for new kitchen tickets, sends each one to its printer on
the local network (raw ESC/POS on port 9100), and tells the server what happened.

Settings, from the environment or from print_agent.ini next to this file:
    BIASHARA_SERVER     https address of the system, e.g. https://pos.example.co.ke
    BIASHARA_PRINT_KEY  the key shown once when a manager added this program

    python print_agent.py            run until stopped
    python print_agent.py --once     collect and print once, then stop (for testing)
"""
import base64
import configparser
import ipaddress
import json
import logging
import os
import socket
import sys
import time
import urllib.error
import urllib.request

VERSION = "1.0"
log = logging.getLogger("print_agent")


def settings(path=None):
    values = {"server": os.environ.get("BIASHARA_SERVER", ""), "key": os.environ.get("BIASHARA_PRINT_KEY", "")}
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "print_agent.ini")
    if os.path.exists(path):
        parser = configparser.ConfigParser()
        parser.read(path, encoding="utf-8")
        section = parser["print_agent"] if parser.has_section("print_agent") else {}
        values["server"] = values["server"] or section.get("server", "")
        values["key"] = values["key"] or section.get("key", "")
    if not values["server"] or not values["key"]:
        raise SystemExit("Set BIASHARA_SERVER and BIASHARA_PRINT_KEY (or fill in print_agent.ini).")
    server = values["server"].rstrip("/")
    if not server.startswith("https://") and not server.startswith("http://localhost") and not server.startswith("http://127.0.0.1"):
        raise SystemExit("BIASHARA_SERVER must be an https:// address.")
    return server, values["key"]


class Server:
    """Talks to the Biashara360 server."""

    def __init__(self, base, key):
        self.base, self.key = base, key

    def _call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method, headers={
            "X-Print-Agent-Key": self.key, "Content-Type": "application/json",
            "User-Agent": "Biashara360-print-agent/" + VERSION})
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode() or "{}")

    def jobs(self):
        return self._call("GET", "/api/print-agent/jobs")

    def report(self, result):
        return self._call("POST", "/api/print-agent/results", result)


def send(host, port, data, timeout=5):
    """Print one ticket. "not_sent": the printer could not be reached, so nothing printed.
    "uncertain": the connection opened but failed, so part of the ticket may have printed."""
    try:
        address = ipaddress.ip_address(host)
        if not address.is_private or address.is_loopback or address.is_unspecified:
            return "not_sent", "Printer must use a local network address"
    except ValueError:
        return "not_sent", "Printer address is not valid"
    try:
        conn = socket.create_connection((host, int(port)), timeout=timeout)
    except OSError as exc:
        return "not_sent", str(exc)[:300]
    try:
        with conn:
            conn.sendall(data)
        return "sent", None
    except OSError as exc:
        return "uncertain", str(exc)[:300]


def run_once(server, printer=send):
    """Collect waiting tickets, print them and report. Returns (printed, poll_seconds)."""
    reply = server.jobs()
    printed = 0
    for job in reply.get("jobs", []):
        status, detail = printer(job["printer_host"], job["printer_port"], base64.b64decode(job["data"]))
        log.info("Ticket %s for %s: %s%s", job["batch_id"], job["department"], status, f" ({detail})" if detail else "")
        result = {"batch_id": job["batch_id"], "department_id": job["department_id"], "claim": job["claim"], "status": status}
        if detail:
            result["detail"] = detail
        for attempt in range(5):  # the ticket is already printed; keep trying to tell the server
            try:
                server.report(result)
                break
            except (urllib.error.URLError, OSError) as exc:
                log.warning("Could not report ticket %s yet: %s", job["batch_id"], exc)
                time.sleep(2 * (attempt + 1))
        printed += status == "sent"
    return printed, int(reply.get("poll_seconds", 3))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    server = Server(*settings())
    log.info("Biashara360 print program %s started for %s", VERSION, server.base)
    wait = 3
    while True:
        try:
            _, wait = run_once(server)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise SystemExit("The server refused this print key. Ask a manager to add the program again and use the new key.")
            log.warning("Server answered %s; trying again shortly", exc.code)
            wait = 15
        except (urllib.error.URLError, OSError) as exc:
            log.warning("Cannot reach the server (%s); trying again shortly", exc)
            wait = 15
        if "--once" in argv:
            return
        time.sleep(max(1, wait))


if __name__ == "__main__":
    main()
