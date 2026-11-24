"""M-Pesa Express (STK push) through Safaricom's Daraja API.

Flow: staff send a prompt -> the customer enters their PIN on their phone -> Safaricom
calls our callback with the result. If the callback is lost, checking the prompt's
status asks Daraja directly (STK push query).

A successful payment is applied to its bill or car wash only if that bill or wash can
still take it (unpaid, same amount). Otherwise the prompt is marked "unmatched" so a
manager can refund or settle it; money is never silently dropped.

Daraja details used here (from Safaricom's Daraja documentation):
- token: GET /oauth/v1/generate?grant_type=client_credentials with Basic auth; tokens last 3600 s.
- prompt: POST /mpesa/stkpush/v1/processrequest; Password = base64(Shortcode + Passkey + Timestamp),
  Timestamp YYYYMMDDHHmmss; TransactionType CustomerPayBillOnline (Paybill) or
  CustomerBuyGoodsOnline (Till, PartyB = Till number); AccountReference <= 12 characters,
  TransactionDesc <= 13 characters.
- status: POST /mpesa/stkpushquery/v1/query with BusinessShortCode, Password, Timestamp, CheckoutRequestID.
- callback: Body.stkCallback with ResultCode (0 = paid) and, when paid, CallbackMetadata.Item
  entries Amount, MpesaReceiptNumber, TransactionDate, PhoneNumber.
"""
import base64
import logging
import re
import threading
import time
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from ..config import get_settings
from ..models import CarWashTransaction, ExternalReceipt, MpesaRequest, Order, OrderStatusHistory, Payment, User
from ..models.operations import BusinessSettings, CashShift
from .audit import record
from .bill_lock import pending, release_table
from .payment_services import matches_order_total

log = logging.getLogger("biashara360.mpesa")

BASE_URLS = {"sandbox": "https://sandbox.safaricom.co.ke", "production": "https://api.safaricom.co.ke"}
# Result codes after which the customer can be prompted again.
RESULT_TEXT = {
    "1": "The customer does not have enough money in M-Pesa.",
    "1032": "The customer cancelled the prompt.",
    "1037": "The customer's phone could not be reached. Check it is on and try again.",
    "1019": "The prompt expired before the customer answered.",
    "2001": "The customer entered the wrong M-Pesa PIN.",
    "1001": "The customer has another M-Pesa transaction in progress. Wait a minute and try again.",
}
# Prompts the customer has not answered after this long are checked with Daraja.
CHECK_AFTER_SECONDS = 20

# Tests replace this with an httpx.MockTransport.
transport: httpx.BaseTransport | None = None
_token: tuple[str, float] | None = None
_token_lock = threading.Lock()


class DarajaError(Exception):
    pass


def base_url():
    settings = get_settings()
    return (settings.mpesa_base_url or BASE_URLS.get(settings.mpesa_environment, BASE_URLS["sandbox"])).rstrip("/")


def _client():
    return httpx.Client(base_url=base_url(), timeout=30, transport=transport)


def require_enabled():
    if not get_settings().mpesa_enabled:
        raise HTTPException(503, "M-Pesa prompts are not set up on this server. Record the M-Pesa receipt by hand.")


def normalize_phone(value: str) -> str:
    """07XX/01XX, +2547XX or 2547XX -> 2547XXXXXXXX (or 2541...)."""
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("0") and len(digits) == 10:
        digits = "254" + digits[1:]
    elif len(digits) == 9 and digits[0] in "71":
        digits = "254" + digits
    if not re.fullmatch(r"254[71]\d{8}", digits):
        raise HTTPException(400, "Enter a Safaricom number such as 0712 345 678.")
    return digits


def _token_value(client):
    global _token
    with _token_lock:
        if _token and _token[1] > time.monotonic():
            return _token[0]
        settings = get_settings()
        r = client.get("/oauth/v1/generate", params={"grant_type": "client_credentials"},
                       auth=(settings.mpesa_consumer_key, settings.mpesa_consumer_secret))
        if r.status_code != 200 or "access_token" not in r.json():
            raise DarajaError(f"M-Pesa sign-in failed ({r.status_code}).")
        body = r.json()
        lifetime = int(body.get("expires_in") or 3599)
        _token = (body["access_token"], time.monotonic() + max(lifetime - 120, 60))
        return _token[0]


def reset_token():
    global _token
    _token = None


def _password():
    settings = get_settings()
    stamp = datetime.now(ZoneInfo(settings.business_timezone)).strftime("%Y%m%d%H%M%S")
    raw = f"{settings.mpesa_shortcode}{settings.mpesa_passkey}{stamp}".encode()
    return base64.b64encode(raw).decode(), stamp


def _post(path, body):
    with _client() as client:
        token = _token_value(client)
        r = client.post(path, json=body, headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 401 or (r.status_code >= 400 and "404.001.03" in r.text):
            reset_token()  # expired or replaced token: sign in again once
            r = client.post(path, json=body, headers={"Authorization": f"Bearer {_token_value(client)}"})
    try:
        data = r.json()
    except ValueError:
        data = {}
    return r.status_code, data


def send_prompt(phone: str, amount: Decimal, reference: str, description: str) -> dict:
    settings = get_settings()
    password, stamp = _password()
    till = settings.mpesa_till_number
    body = {
        "BusinessShortCode": settings.mpesa_shortcode, "Password": password, "Timestamp": stamp,
        "TransactionType": "CustomerBuyGoodsOnline" if till else "CustomerPayBillOnline",
        "Amount": int(amount), "PartyA": phone, "PartyB": till or settings.mpesa_shortcode,
        "PhoneNumber": phone,
        "CallBackURL": f"{settings.mpesa_callback_url.rstrip('/')}/api/mpesa/callback/{settings.mpesa_callback_token}",
        "AccountReference": reference[:12], "TransactionDesc": description[:13],
    }
    status, data = _post("/mpesa/stkpush/v1/processrequest", body)
    if status != 200 or str(data.get("ResponseCode")) != "0" or not data.get("CheckoutRequestID"):
        message = data.get("errorMessage") or data.get("ResponseDescription") or f"HTTP {status}"
        log.warning("M-Pesa prompt refused: %s %s", status, data)
        raise DarajaError(f"M-Pesa did not accept the prompt: {message}")
    return data


def query_prompt(checkout_request_id: str) -> dict | None:
    """Daraja's view of a prompt, or None while it is still being processed."""
    settings = get_settings()
    password, stamp = _password()
    status, data = _post("/mpesa/stkpushquery/v1/query", {
        "BusinessShortCode": settings.mpesa_shortcode, "Password": password, "Timestamp": stamp,
        "CheckoutRequestID": checkout_request_id})
    if status == 200 and "ResultCode" in data:
        return data
    log.info("M-Pesa status not final yet: %s %s", status, data)
    return None


# ---- applying results -------------------------------------------------------------------

def _active_shift(db, user_id):
    return db.scalar(select(CashShift).where(CashShift.active_cashier_id == user_id))


def _apply_to_order(db, req: MpesaRequest, staff: User, now):
    order = db.scalar(select(Order).where(Order.id == req.order_id).with_for_update())
    if order is None or order.status in ("cleared", "completed", "cancelled"):
        return "the bill is already closed"
    if db.scalar(select(Payment.id).where(Payment.order_id == order.id, Payment.status != "rejected")):
        return "another payment was already recorded for the bill"
    if pending(db, order.id):
        return "the bill has change requests waiting"
    if not matches_order_total(req.paid_amount, order.total):
        return f"the bill total is now {order.total:.2f}"
    from ..utils.helpers import order_dict
    snapshot = order_dict(order)
    business = db.get(BusinessSettings, 1)
    shift = _active_shift(db, req.created_by)
    payment = Payment(order_id=order.id, active_order_id=order.id, amount=req.paid_amount, method="m-pesa",
                      status="completed", reference=req.receipt, notes="Paid by M-Pesa prompt",
                      shift_id=shift.id if shift else None, recorded_by=req.created_by, completed_at=now,
                      receipt_snapshot=jsonable_encoder(
                          {k: snapshot[k] for k in ("order_number", "table_number", "waiter", "items", "tax_summary", "total")}
                          | {"business": business.values if business else {"business_name": "Biashara360"}}))
    order.status = "cleared"; order.cleared_at = now; order.version += 1
    release_table(db, order)
    db.add(payment)
    db.add(OrderStatusHistory(order_id=order.id, status="cleared", changed_by=req.created_by))
    db.flush()
    req.payment_id = payment.id
    if req.receipt:
        db.add(ExternalReceipt(reference=req.receipt, source="payment", source_id=payment.id))
    record(db, staff, "mpesa_prompt_paid", "payments", payment.id,
           after={"amount": payment.amount, "receipt": req.receipt, "prompt": req.id})
    return None


def _apply_to_wash(db, req: MpesaRequest, staff: User, now):
    wash = db.scalar(select(CarWashTransaction).where(CarWashTransaction.id == req.carwash_id).with_for_update())
    if wash is None or wash.payment_status != "pending" or wash.payment_method != "m-pesa":
        return "the car wash is already paid"
    if not matches_order_total(req.paid_amount, wash.amount):
        return f"the car wash costs {wash.amount:.2f}"
    wash.payment_status = "completed"; wash.completed_at = now
    if req.receipt:
        wash.mpesa_reference = req.receipt
        db.add(ExternalReceipt(reference=req.receipt, source="carwash", source_id=wash.id))
    record(db, staff, "mpesa_prompt_paid", "carwash", wash.id, after={"amount": wash.amount, "receipt": req.receipt, "prompt": req.id})
    return None


def _receipt_taken(db, receipt, req):
    if not receipt:
        return False
    other = db.scalar(select(MpesaRequest.id).where(MpesaRequest.receipt == receipt, MpesaRequest.id != req.id))
    return bool(other or db.get(ExternalReceipt, receipt))


def mark_paid(db, req: MpesaRequest, amount, receipt=None, phone=None):
    """Record a successful payment and apply it. Safe to call twice."""
    now = datetime.utcnow()
    if req.status in ("paid", "unmatched", "resolved"):
        # Already handled; a late callback may still bring the receipt number.
        if receipt and not req.receipt and not _receipt_taken(db, receipt, req):
            req.receipt = receipt
            if req.payment_id:
                payment = db.get(Payment, req.payment_id)
                if payment and not payment.reference:
                    payment.reference = receipt
                    db.add(ExternalReceipt(reference=receipt, source="payment", source_id=payment.id))
            elif req.carwash_id and req.status == "paid":
                wash = db.get(CarWashTransaction, req.carwash_id)
                if wash and not wash.mpesa_reference:
                    wash.mpesa_reference = receipt
                    db.add(ExternalReceipt(reference=receipt, source="carwash", source_id=wash.id))
        return
    if _receipt_taken(db, receipt, req):
        log.error("M-Pesa receipt %s reported twice; prompt %s kept for review", receipt, req.id)
        req.status, req.note, req.finished_at = "unmatched", f"Receipt {receipt} was already used.", now
        return
    req.paid_amount = amount if amount is not None else req.amount
    req.receipt, req.paid_phone, req.finished_at = receipt, phone, now
    req.result_code, req.result_desc = "0", req.result_desc or "Paid"
    staff = db.get(User, req.created_by)
    problem = _apply_to_order(db, req, staff, now) if req.order_id else _apply_to_wash(db, req, staff, now)
    if problem:
        req.status, req.note = "unmatched", f"Paid, but {problem}. Refund the customer or settle it by hand."
        log.warning("M-Pesa prompt %s unmatched: %s", req.id, problem)
    else:
        req.status = "paid"


def mark_failed(db, req: MpesaRequest, code, desc):
    if req.status != "waiting":
        return
    req.status, req.result_code, req.result_desc = "failed", str(code), (desc or "")[:300]
    req.finished_at = datetime.utcnow()


def handle_callback(db, payload: dict):
    callback = (payload or {}).get("Body", {}).get("stkCallback") or {}
    checkout = callback.get("CheckoutRequestID")
    req = db.scalar(select(MpesaRequest).where(MpesaRequest.checkout_request_id == checkout).with_for_update()) if checkout else None
    if req is None:
        log.warning("M-Pesa callback for an unknown prompt: %s", checkout)
        return
    req.callback = payload
    code = str(callback.get("ResultCode"))
    if code == "0":
        items = {i.get("Name"): i.get("Value") for i in (callback.get("CallbackMetadata") or {}).get("Item", [])}
        amount = Decimal(str(items["Amount"])) if items.get("Amount") is not None else None
        receipt = str(items["MpesaReceiptNumber"]).strip().upper() if items.get("MpesaReceiptNumber") else None
        phone = str(items["PhoneNumber"]) if items.get("PhoneNumber") else None
        mark_paid(db, req, amount, receipt, phone)
    else:
        mark_failed(db, req, code, callback.get("ResultDesc"))


def refresh(db, req: MpesaRequest):
    """Ask Daraja about a prompt that has had no callback for a while."""
    if req.status != "waiting" or not req.checkout_request_id:
        return
    if (datetime.utcnow() - req.created_at).total_seconds() < CHECK_AFTER_SECONDS:
        return
    if req.checked_at and (datetime.utcnow() - req.checked_at).total_seconds() < 10:
        return
    req.checked_at = datetime.utcnow()
    try:
        data = query_prompt(req.checkout_request_id)
    except (DarajaError, httpx.HTTPError) as exc:
        log.warning("M-Pesa status check failed: %s", exc)
        return
    if not data:
        return
    code = str(data.get("ResultCode"))
    if code == "0":
        mark_paid(db, req, None)  # the receipt number arrives with the callback
    else:
        mark_failed(db, req, code, data.get("ResultDesc"))


def message(req: MpesaRequest):
    if req.status == "waiting":
        return "Waiting for the customer to enter their M-Pesa PIN."
    if req.status == "paid":
        return "Paid" + (f". Receipt {req.receipt}." if req.receipt else ". The receipt number will follow.")
    if req.status == "failed":
        return RESULT_TEXT.get(req.result_code or "", req.result_desc or "The payment did not go through.")
    return req.note or req.status
