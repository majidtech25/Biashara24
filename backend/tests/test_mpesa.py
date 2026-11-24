"""M-Pesa Express prompts, tested against a fake Daraja server."""
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
SETTINGS = {"MPESA_CONSUMER_KEY": "key", "MPESA_CONSUMER_SECRET": "secret", "MPESA_SHORTCODE": "174379",
            "MPESA_PASSKEY": "passkey", "MPESA_CALLBACK_URL": "https://pos.example.test",
            "MPESA_CALLBACK_TOKEN": TOKEN}


class FakeDaraja:
    """Answers like Daraja and remembers every request."""

    def __init__(self):
        self.requests, self.query_result, self.count = [], None, 0

    def __call__(self, request: httpx.Request):
        self.requests.append(request)
        if request.url.path == "/oauth/v1/generate":
            assert request.url.params["grant_type"] == "client_credentials"
            assert request.headers["Authorization"] == "Basic " + base64.b64encode(b"key:secret").decode()
            return httpx.Response(200, json={"access_token": "token-1", "expires_in": "3599"})
        assert request.headers["Authorization"] == "Bearer token-1"
        if request.url.path == "/mpesa/stkpush/v1/processrequest":
            self.count += 1
            return httpx.Response(200, json={"MerchantRequestID": f"m-{self.count}", "CheckoutRequestID": f"ws_CO_{uuid4().hex}",
                                             "ResponseCode": "0", "ResponseDescription": "Success. Request accepted for processing",
                                             "CustomerMessage": "Success. Request accepted for processing"})
        if request.url.path == "/mpesa/stkpushquery/v1/query":
            if self.query_result is None:
                return httpx.Response(500, json={"errorCode": "500.001.1001", "errorMessage": "The transaction is being processed"})
            return httpx.Response(200, json={"ResponseCode": "0", "ResultCode": self.query_result, "ResultDesc": "done"})
        return httpx.Response(404)

    def pushes(self):
        return [json.loads(r.content) for r in self.requests if r.url.path.endswith("processrequest")]


@pytest.fixture
def daraja(monkeypatch):
    for key, value in SETTINGS.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    fake = FakeDaraja()
    monkeypatch.setattr(mpesa, "transport", httpx.MockTransport(fake))
    mpesa.reset_token()
    yield fake
    mpesa.reset_token()
    get_settings.cache_clear()


def paid(checkout, amount, receipt, phone=254712345678):
    return {"Body": {"stkCallback": {"MerchantRequestID": "m", "CheckoutRequestID": checkout, "ResultCode": 0,
            "ResultDesc": "The service request is processed successfully.", "CallbackMetadata": {"Item": [
                {"Name": "Amount", "Value": amount}, {"Name": "MpesaReceiptNumber", "Value": receipt},
                {"Name": "TransactionDate", "Value": 20261124150000}, {"Name": "PhoneNumber", "Value": phone}]}}}}


def failed(checkout, code=1032, desc="Request cancelled by user"):
    return {"Body": {"stkCallback": {"MerchantRequestID": "m", "CheckoutRequestID": checkout, "ResultCode": code, "ResultDesc": desc}}}


def checkout_of(fake, prompt_id):
    from app.database import SessionLocal
    from app.models import MpesaRequest
    with SessionLocal() as db:
        return db.get(MpesaRequest, prompt_id).checkout_request_id


def receipt():
    return "T" + uuid4().hex[:9].upper()


def test_bill_is_cleared_when_the_customer_pays(daraja):
    with TestClient(app) as c:
        director, cashier = login(c), login(c, "cashier@gmail.com", "cashier123")
        order = new_order(c, director)
        r = c.post("/api/mpesa/prompts", headers=cashier, json={"order_id": order["id"], "phone": "0712 345 678",
                                                               "expected_version": order["version"]})
        assert r.status_code == 201, r.text
        prompt = r.json()
        assert prompt["status"] == "waiting" and prompt["phone"] == "25471****678"

        body = daraja.pushes()[-1]
        assert body["TransactionType"] == "CustomerPayBillOnline" and body["PartyB"] == "174379"
        assert body["PartyA"] == body["PhoneNumber"] == "254712345678" and body["Amount"] == 320
        assert base64.b64decode(body["Password"]).decode() == "174379passkey" + body["Timestamp"]
        assert len(body["Timestamp"]) == 14 and len(body["AccountReference"]) <= 12 and len(body["TransactionDesc"]) <= 13
        assert body["CallBackURL"] == f"https://pos.example.test/api/mpesa/callback/{TOKEN}"

        # A second prompt for the same bill waits for the first.
        assert c.post("/api/mpesa/prompts", headers=cashier, json={"order_id": order["id"], "phone": "0712345678",
                      "expected_version": order["version"]}).status_code == 409

        checkout, number = checkout_of(daraja, prompt["id"]), receipt()
        assert c.post("/api/mpesa/callback/wrong-token", json=paid(checkout, 320, number)).status_code == 404
        r = c.post(f"/api/mpesa/callback/{TOKEN}", json=paid(checkout, 320.0, number))
        assert r.status_code == 200 and r.json()["ResultCode"] == 0
        c.post(f"/api/mpesa/callback/{TOKEN}", json=paid(checkout, 320.0, number))  # Safaricom may send it twice

        status = c.get(f"/api/mpesa/prompts/{prompt['id']}", headers=cashier).json()
        assert status["status"] == "paid" and status["receipt"] == number
        bill = c.get(f"/api/orders/{order['id']}", headers=cashier).json()
        assert bill["status"] == "cleared"
        payments = [p for p in c.get("/api/payments", headers=cashier).json() if p["order_id"] == order["id"]]
        assert len(payments) == 1 and payments[0]["status"] == "completed" and payments[0]["reference"] == number
        # The receipt cannot be typed in again for another bill.
        other = new_order(c, director)
        r = c.post(f"/api/orders/{other['id']}/clear", headers=cashier, json={"expected_version": other["version"],
                   "amount": 320, "method": "m-pesa", "reference": number})
        assert r.status_code == 409


def test_cancelled_prompt_can_be_sent_again(daraja):
    with TestClient(app) as c:
        director, cashier = login(c), login(c, "cashier@gmail.com", "cashier123")
        order = new_order(c, director)
        send = lambda: c.post("/api/mpesa/prompts", headers=cashier, json={"order_id": order["id"], "phone": "+254712345678",
                                                                           "expected_version": order["version"]})
        first = send().json()
        c.post(f"/api/mpesa/callback/{TOKEN}", json=failed(checkout_of(daraja, first["id"])))
        status = c.get(f"/api/mpesa/prompts/{first['id']}", headers=cashier).json()
        assert status["status"] == "failed" and status["message"] == "The customer cancelled the prompt."
        assert c.get(f"/api/orders/{order['id']}", headers=cashier).json()["status"] != "cleared"
        assert send().status_code == 201


def test_lost_callback_is_recovered_by_checking_with_mpesa(daraja, monkeypatch):
    monkeypatch.setattr(mpesa, "CHECK_AFTER_SECONDS", 0)
    with TestClient(app) as c:
        director, cashier = login(c), login(c, "cashier@gmail.com", "cashier123")
        order = new_order(c, director)
        prompt = c.post("/api/mpesa/prompts", headers=cashier, json={"order_id": order["id"], "phone": "0712345678",
                        "expected_version": order["version"]}).json()
        # Still being processed: nothing changes.
        assert c.get(f"/api/mpesa/prompts/{prompt['id']}", headers=cashier).json()["status"] == "waiting"
        daraja.query_result = "0"
        from app.database import SessionLocal
        from app.models import MpesaRequest
        with SessionLocal() as db:  # allow the next check straight away
            db.get(MpesaRequest, prompt["id"]).checked_at = None; db.commit()
        status = c.get(f"/api/mpesa/prompts/{prompt['id']}", headers=cashier).json()
        assert status["status"] == "paid" and status["receipt"] is None
        assert c.get(f"/api/orders/{order['id']}", headers=cashier).json()["status"] == "cleared"
        # The callback arrives late and fills in the receipt number.
        number = receipt()
        c.post(f"/api/mpesa/callback/{TOKEN}", json=paid(checkout_of(daraja, prompt["id"]), 320, number))
        assert c.get(f"/api/mpesa/prompts/{prompt['id']}", headers=cashier).json()["receipt"] == number
        payment = [p for p in c.get("/api/payments", headers=cashier).json() if p["order_id"] == order["id"]][0]
        assert payment["reference"] == number


def test_payment_after_the_bill_was_paid_another_way_is_kept_for_a_manager(daraja):
    with TestClient(app) as c:
        director, cashier = login(c), login(c, "cashier@gmail.com", "cashier123")
        manager = login(c, "manager@gmail.com", "manager123")
        order = new_order(c, director)
        prompt = c.post("/api/mpesa/prompts", headers=cashier, json={"order_id": order["id"], "phone": "0712345678",
                        "expected_version": order["version"]}).json()
        assert c.post(f"/api/mpesa/prompts/{prompt['id']}/stop", headers=cashier).json()["status"] == "failed"
        current = c.get(f"/api/orders/{order['id']}", headers=cashier).json()
        r = c.post(f"/api/orders/{order['id']}/clear", headers=cashier, json={"expected_version": current["version"],
                   "amount": 320, "method": "cash"})
        assert r.status_code == 201, r.text
        # The customer pays the old prompt anyway.
        c.post(f"/api/mpesa/callback/{TOKEN}", json=paid(checkout_of(daraja, prompt["id"]), 320, receipt()))
        status = c.get(f"/api/mpesa/prompts/{prompt['id']}", headers=cashier).json()
        assert status["status"] == "unmatched" and "already closed" in status["note"]
        assert len([p for p in c.get("/api/payments", headers=cashier).json() if p["order_id"] == order["id"]]) == 1
        assert prompt["id"] in [p["id"] for p in c.get("/api/mpesa/prompts?status=unmatched", headers=manager).json()]
        assert c.post(f"/api/mpesa/prompts/{prompt['id']}/resolve", headers=cashier, json={"note": "Refunded"}).status_code == 403
        r = c.post(f"/api/mpesa/prompts/{prompt['id']}/resolve", headers=manager, json={"note": "Refunded to customer"})
        assert r.status_code == 200 and r.json()["status"] == "resolved"


def test_car_wash_paid_by_prompt(daraja):
    with TestClient(app) as c:
        wash_manager = login(c, "carwash@gmail.com", "carwash123")
        bay, service, _ = carwash_setup(c, wash_manager)
        assert _wash(c, wash_manager, bay, service, payment_method="m-pesa").status_code == 400  # no receipt, no prompt
        r = _wash(c, wash_manager, bay, service, payment_method="m-pesa", mpesa_prompt=True)
        assert r.status_code == 201, r.text
        wash = r.json()
        assert wash["payment_status"] == "pending" and wash["mpesa_reference"] is None
        # Pending prompt washes cannot be confirmed by hand without a receipt number.
        assert c.post(f"/api/carwash/{wash['id']}/complete", headers=wash_manager).status_code == 400
        prompt = c.post("/api/mpesa/prompts", headers=wash_manager, json={"carwash_id": wash["id"], "phone": "0712345678"})
        assert prompt.status_code == 201, prompt.text
        number = receipt()
        c.post(f"/api/mpesa/callback/{TOKEN}", json=paid(checkout_of(daraja, prompt.json()["id"]), 800, number))
        done = [x for x in c.get("/api/carwash/history", headers=wash_manager).json()["transactions"] if x["id"] == wash["id"]][0]
        assert done["payment_status"] == "completed" and done["mpesa_reference"] == number
        # Car-wash staff cannot prompt for restaurant bills.
        assert c.post("/api/mpesa/prompts", headers=wash_manager, json={"order_id": 1, "phone": "0712345678"}).status_code == 403


def test_till_numbers_use_buy_goods(daraja, monkeypatch):
    monkeypatch.setenv("MPESA_TILL_NUMBER", "5551234")
    get_settings.cache_clear()
    with TestClient(app) as c:
        director, cashier = login(c), login(c, "cashier@gmail.com", "cashier123")
        order = new_order(c, director)
        r = c.post("/api/mpesa/prompts", headers=cashier, json={"order_id": order["id"], "phone": "0112345678",
                   "expected_version": order["version"]})
        assert r.status_code == 201, r.text
        body = daraja.pushes()[-1]
        assert body["TransactionType"] == "CustomerBuyGoodsOnline" and body["PartyB"] == "5551234"
        assert body["BusinessShortCode"] == "174379" and body["PartyA"] == "254112345678"


def test_prompts_are_off_until_configured():
    get_settings.cache_clear()
    with TestClient(app) as c:
        cashier = login(c, "cashier@gmail.com", "cashier123")
        assert c.get("/api/mpesa/config", headers=cashier).json()["enabled"] is False
        r = c.post("/api/mpesa/prompts", headers=cashier, json={"order_id": 1, "phone": "0712345678"})
        assert r.status_code == 503
        assert c.post(f"/api/mpesa/callback/{TOKEN}", json={}).status_code == 404


@pytest.mark.parametrize("raw,expected", [("0712345678", "254712345678"), ("+254 712 345 678", "254712345678"),
                                          ("0112345678", "254112345678"), ("712345678", "254712345678")])
def test_phone_numbers(raw, expected):
    assert mpesa.normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["12345", "0812345678", "2547123456789"])
def test_bad_phone_numbers(raw):
    with pytest.raises(Exception):
        mpesa.normalize_phone(raw)
