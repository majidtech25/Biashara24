"""M-Pesa Paybill: bill details and QR code, Safaricom's payment notices, and cashiers
confirming payments. Daraja is replaced by a fake server."""
import base64
import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.services import mpesa
from test_carwash import _setup as carwash_setup, _wash
from test_integration import login, new_order

TOKEN = "callback-secret-" + "x" * 16
SETTINGS = {"MPESA_CONSUMER_KEY": "key", "MPESA_CONSUMER_SECRET": "secret", "MPESA_SHORTCODE": "600996",
            "MPESA_BUSINESS_NAME": "Mama Pima Grill", "MPESA_CALLBACK_URL": "https://pos.example.test",
            "MPESA_CALLBACK_TOKEN": TOKEN}
PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode()


class FakeDaraja:
    def __init__(self):
        self.requests = []

    def __call__(self, request: httpx.Request):
        self.requests.append(request)
        if request.url.path == "/oauth/v1/generate":
            assert request.headers["Authorization"] == "Basic " + base64.b64encode(b"key:secret").decode()
            return httpx.Response(200, json={"access_token": "token-1", "expires_in": "3599"})
        assert request.headers["Authorization"] == "Bearer token-1"
        if request.url.path == "/mpesa/qrcode/v1/generate":
            return httpx.Response(200, json={"ResponseCode": "00", "ResponseDescription": "The service request is processed successfully.",
                                             "QRCode": PNG})
        if request.url.path == "/mpesa/c2b/v2/registerurl":
            return httpx.Response(200, json={"OriginatorCoversationID": "abc", "ResponseCode": "0", "ResponseDescription": "Success"})
        return httpx.Response(404)

    def bodies(self, suffix):
        return [json.loads(r.content) for r in self.requests if r.url.path.endswith(suffix)]


@pytest.fixture
def daraja(monkeypatch):
    for key, value in SETTINGS.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    fake = FakeDaraja()
    monkeypatch.setattr(mpesa, "transport", httpx.MockTransport(fake))
    mpesa.reset()
    yield fake
    mpesa.reset()
    get_settings.cache_clear()


def notice(account, amount, receipt=None, shortcode="600996"):
    receipt = receipt or "T" + uuid4().hex[:9].upper()
    return receipt, {"TransactionType": "Pay Bill", "TransID": receipt, "TransTime": "20261124153000",
                     "TransAmount": f"{amount:.2f}", "BusinessShortCode": shortcode, "BillRefNumber": account,
                     "InvoiceNumber": "", "OrgAccountBalance": "1000.00", "ThirdPartyTransID": "",
                     "MSISDN": "2547 ***** 678", "FirstName": "WANJIKU", "MiddleName": "null", "LastName": ""}


def pay(c, body):
    r = c.post(f"/api/c2b/{TOKEN}/confirmation", json=body)
    assert r.status_code == 200 and r.json()["ResultCode"] == 0
    return r


def test_bill_shows_paybill_account_and_qr(daraja):
    with TestClient(app) as c:
        director, waiter = login(c), login(c, "waiter@gmail.com", "waiter123")
        order = new_order(c, director)
        r = c.get(f"/api/paybill/bill?order_id={order['id']}", headers=director)
        assert r.status_code == 200, r.text
        bill = r.json()
        assert bill["paybill"] == "600996" and bill["amount"] == 320 and bill["qr"] == PNG
        assert bill["account"] == order["order_number"].replace("-", "") and len(bill["account"]) <= 20
        qr = daraja.bodies("qrcode/v1/generate")[-1]
        assert qr == {"MerchantName": "Mama Pima Grill", "RefNo": bill["account"], "Amount": 320, "TrxCode": "PB",
                      "CPI": "600996", "Size": "300"}
        c.get(f"/api/paybill/bill?order_id={order['id']}", headers=director)
        assert len(daraja.bodies("qrcode/v1/generate")) == 1  # the same QR code is reused
        # The waiter who took the order can print its bill.
        assert c.get(f"/api/paybill/bill?order_id={order['id']}", headers=waiter).status_code == 200


def test_payment_notice_lets_the_cashier_confirm_in_one_step(daraja):
    with TestClient(app) as c:
        director, cashier = login(c), login(c, "cashier@gmail.com", "cashier123")
        order = new_order(c, director)
        account = c.get(f"/api/paybill/bill?order_id={order['id']}", headers=cashier).json()["account"]
        # Customers type account numbers loosely; Safaricom may send the notice twice.
        receipt, body = notice(account.lower()[:3] + " " + account[3:], 320)
        assert c.post("/api/c2b/wrong-token/confirmation", json=body).status_code == 404
        pay(c, body); pay(c, body)
        bill = c.get(f"/api/paybill/bill?order_id={order['id']}", headers=cashier).json()
        assert [(p["receipt"], p["status"], p["order_id"]) for p in bill["payments"]] == [(receipt, "received", order["id"])]
        assert bill["payments"][0]["payer"] == "WANJIKU" and bill["payments"][0]["phone"] == "2547 ***** 678"

        # The bill is not paid until the cashier confirms it.
        assert c.get(f"/api/orders/{order['id']}", headers=cashier).json()["status"] != "cleared"
        r = c.post(f"/api/orders/{order['id']}/clear", headers=cashier, json={"expected_version": order["version"],
                   "amount": 320, "method": "m-pesa", "reference": receipt.lower()})
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "completed" and r.json()["reference"] == receipt
        assert c.get(f"/api/orders/{order['id']}", headers=cashier).json()["status"] == "cleared"
        used = c.get(f"/api/paybill/payments?q={receipt}", headers=cashier).json()
        assert used[0]["status"] == "used"

        # The same receipt cannot pay a second bill.
        other = new_order(c, director)
        r = c.post(f"/api/orders/{other['id']}/clear", headers=cashier, json={"expected_version": other["version"],
                   "amount": 320, "method": "m-pesa", "reference": receipt})
        assert r.status_code == 409


def test_wrong_amount_is_refused_and_unknown_receipts_wait(daraja):
    with TestClient(app) as c:
        director, cashier = login(c), login(c, "cashier@gmail.com", "cashier123")
        order = new_order(c, director)
        receipt, body = notice("NOSUCHBILL", 300)
        pay(c, body)
        unmatched = c.get("/api/paybill/payments?status=received", headers=cashier).json()
        assert receipt in [p["receipt"] for p in unmatched if p["order_id"] is None]
        r = c.post(f"/api/orders/{order['id']}/clear", headers=cashier, json={"expected_version": order["version"],
                   "amount": 320, "method": "m-pesa", "reference": receipt})
        assert r.status_code == 400 and "KES 300.00" in r.json()["detail"]
        # A receipt Safaricom has not reported waits for confirmation, as before.
        pending = "Q" + uuid4().hex[:9].upper()
        r = c.post(f"/api/orders/{order['id']}/clear", headers=cashier, json={"expected_version": order["version"],
                   "amount": 320, "method": "m-pesa", "reference": pending})
        assert r.status_code == 201 and r.json()["status"] == "pending"
        # When Safaricom's notice arrives, the waiting entry is confirmed by itself.
        _, late = notice("ANYTHING", 320, receipt=pending)
        pay(c, late)
        assert c.get(f"/api/orders/{order['id']}", headers=cashier).json()["status"] == "cleared"
        payment = [p for p in c.get("/api/payments", headers=cashier).json() if p["order_id"] == order["id"]][0]
        assert payment["status"] == "completed"


def test_car_wash_paid_by_paybill(daraja):
    with TestClient(app) as c:
        manager = login(c, "carwash@gmail.com", "carwash123")
        bay, service, _ = carwash_setup(c, manager)
        assert _wash(c, manager, bay, service, payment_method="m-pesa").status_code == 400
        wash = _wash(c, manager, bay, service, payment_method="m-pesa", pay_later=True).json()
        assert wash["payment_status"] == "pending"
        details = c.get(f"/api/paybill/bill?carwash_id={wash['id']}", headers=manager).json()
        receipt, body = notice(details["account"], 800)
        pay(c, body)
        details = c.get(f"/api/paybill/bill?carwash_id={wash['id']}", headers=manager).json()
        assert details["payments"][0]["receipt"] == receipt
        assert c.post(f"/api/carwash/{wash['id']}/complete", headers=manager).status_code == 400  # receipt needed
        r = c.post(f"/api/carwash/{wash['id']}/complete", headers=manager, json={"mpesa_reference": receipt})
        assert r.status_code == 200 and r.json()["payment_status"] == "completed"
        assert c.get(f"/api/paybill/payments?q={receipt}", headers=manager).json()[0]["status"] == "used"


def test_registering_addresses_with_safaricom(daraja):
    with TestClient(app) as c:
        director, manager = login(c), login(c, "manager@gmail.com", "manager123")
        assert c.post("/api/paybill/register", headers=manager).status_code == 403
        r = c.post("/api/paybill/register", headers=director)
        assert r.status_code == 200, r.text
        body = daraja.bodies("registerurl")[-1]
        assert body["ShortCode"] == "600996" and body["ResponseType"] == "Completed"
        assert body["ConfirmationURL"] == f"https://pos.example.test/api/c2b/{TOKEN}/confirmation"
        assert body["ValidationURL"] == f"https://pos.example.test/api/c2b/{TOKEN}/validation"
        for url in (body["ConfirmationURL"], body["ValidationURL"]):  # words Safaricom rejects in URLs
            assert not any(word in url.lower() for word in ("mpesa", "m-pesa", "safaricom", "exe", "cmd", "sql", "query"))
        assert c.post(f"/api/c2b/{TOKEN}/validation", json={}).json() == {"ResultCode": "0", "ResultDesc": "Accepted"}


def test_payments_for_another_paybill_are_ignored(daraja):
    with TestClient(app) as c:
        cashier = login(c, "cashier@gmail.com", "cashier123")
        receipt, body = notice("X", 100, shortcode="111111")
        pay(c, body)
        assert c.get(f"/api/paybill/payments?q={receipt}", headers=cashier).json() == []


def test_without_keys_the_bill_still_shows_the_paybill(monkeypatch):
    monkeypatch.setenv("MPESA_SHORTCODE", "600996")
    get_settings.cache_clear()
    try:
        with TestClient(app) as c:
            director = login(c)
            order = new_order(c, director)
            bill = c.get(f"/api/paybill/bill?order_id={order['id']}", headers=director).json()
            assert bill["paybill"] == "600996" and bill["qr"] is None and "Daraja keys" in bill["qr_note"]
            assert c.post(f"/api/c2b/{TOKEN}/confirmation", json={}).status_code == 404
    finally:
        get_settings.cache_clear()


def test_part_paid_bill_shows_what_is_left(daraja):
    with TestClient(app) as c:
        director = login(c)
        order = new_order(c, director)
        r = c.post(f"/api/orders/{order['id']}/clear", headers=director, json={"expected_version": order["version"], "amount": 120,
                   "method": "cash", "part_payment": True})
        assert r.status_code == 201, r.text
        bill = c.get(f"/api/paybill/bill?order_id={order['id']}", headers=director).json()
        assert bill["amount"] == 200 and daraja.bodies("qrcode/v1/generate")[-1]["Amount"] == 200
