"""M-Pesa Paybill through Safaricom's Daraja API: payment monitoring and bill QR codes.

The system never asks a customer to pay. The printed bill shows the Paybill number,
the bill number as the account number, and an M-Pesa QR code. Safaricom then tells
us about every payment into the Paybill (C2B confirmation). A cashier sees the
payments received for a bill and confirms one; typing a receipt number by hand is
checked against what Safaricom reported.

Daraja details used here (from copies of Safaricom's Daraja documentation, see DEPLOYMENT.md):
- token: GET /oauth/v1/generate?grant_type=client_credentials with Basic auth; tokens last 3600 s.
- register: POST /mpesa/c2b/v2/registerurl with ShortCode, ResponseType, ConfirmationURL,
  ValidationURL. Production URLs must be HTTPS and must not contain words such as
  "mpesa" or "safaricom". Production URLs are registered once.
- confirmation body: TransactionType, TransID, TransTime, TransAmount, BusinessShortCode,
  BillRefNumber, MSISDN (masked), FirstName...; we answer ResultCode 0.
- QR: POST /mpesa/qrcode/v1/generate with MerchantName, RefNo, Amount, TrxCode "PB",
  CPI (the Paybill number), Size; the reply's QRCode is a base64 PNG.
"""
import logging
import threading
import time
from collections import OrderedDict
from datetime import datetime
from decimal import Decimal

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select

from ..config import get_settings
from ..models import C2BPayment, CarWashTransaction, Order, Payment

log = logging.getLogger("biashara360.mpesa")

BASE_URLS = {"sandbox": "https://sandbox.safaricom.co.ke", "production": "https://api.safaricom.co.ke"}

# Tests replace this with an httpx.MockTransport.
transport: httpx.BaseTransport | None = None
_token: tuple[str, float] | None = None
_lock = threading.Lock()
_qr_cache: "OrderedDict[tuple, str]" = OrderedDict()


class DarajaError(Exception):
    pass


def enabled() -> bool:
    return get_settings().mpesa_enabled


def base_url():
    settings = get_settings()
    return (settings.mpesa_base_url or BASE_URLS.get(settings.mpesa_environment, BASE_URLS["sandbox"])).rstrip("/")


def reset():
    global _token
    _token = None
    _qr_cache.clear()


def _token_value(client):
    global _token
    with _lock:
        if _token and _token[1] > time.monotonic():
            return _token[0]
        settings = get_settings()
        r = client.get("/oauth/v1/generate", params={"grant_type": "client_credentials"},
                       auth=(settings.mpesa_consumer_key, settings.mpesa_consumer_secret))
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code != 200 or "access_token" not in body:
            raise DarajaError(f"M-Pesa sign-in failed ({r.status_code}).")
        lifetime = int(body.get("expires_in") or 3599)
        _token = (body["access_token"], time.monotonic() + max(lifetime - 120, 60))
        return _token[0]


def _post(path, body):
    with httpx.Client(base_url=base_url(), timeout=30, transport=transport) as client:
        token = _token_value(client)
        r = client.post(path, json=body, headers={"Authorization": f"Bearer {token}"})
        if r.status_code in (401, 404) and "Invalid Access Token" in r.text:
            reset_token_only()
            r = client.post(path, json=body, headers={"Authorization": f"Bearer {_token_value(client)}"})
    try:
        data = r.json()
    except ValueError:
        data = {}
    return r.status_code, data


def reset_token_only():
    global _token
    _token = None


# ---- account numbers --------------------------------------------------------------------

def clean_account(value) -> str:
    """Customers type account numbers by hand: ignore case, spaces and dashes."""
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def account_for(order: Order | None = None, wash: CarWashTransaction | None = None) -> str:
    """The account number printed on a bill: its bill number without dashes (at most 20 characters)."""
    return clean_account(order.order_number if order is not None else wash.transaction_number)[:20]


def match_account(db, account: str):
    """The open bill or car wash an account number belongs to, if any."""
    key = clean_account(account)
    if not key:
        return None, None
    order = db.scalar(select(Order).where(func.upper(func.replace(Order.order_number, "-", "")) == key)
                      .execution_options(all_branches=True))
    if order is not None:
        return order, None
    wash = db.scalar(select(CarWashTransaction).where(
        func.upper(func.replace(CarWashTransaction.transaction_number, "-", "")) == key).execution_options(all_branches=True))
    return None, wash


# ---- Safaricom calls --------------------------------------------------------------------

def callback_urls():
    settings = get_settings()
    root = f"{settings.mpesa_callback_url.rstrip('/')}/api/c2b/{settings.mpesa_callback_token}"
    return f"{root}/confirmation", f"{root}/validation"


def register_urls() -> dict:
    """Tell Safaricom where to send Paybill payments. In production this is done once."""
    settings = get_settings()
    confirmation, validation = callback_urls()
    status, data = _post("/mpesa/c2b/v2/registerurl", {
        "ShortCode": settings.mpesa_shortcode, "ResponseType": "Completed",
        "ConfirmationURL": confirmation, "ValidationURL": validation})
    if status != 200 or str(data.get("ResponseCode")) != "0":
        raise DarajaError(data.get("errorMessage") or data.get("ResponseDescription") or f"HTTP {status}")
    return data


def qr_code(account: str, amount: Decimal) -> str:
    """Base64 PNG of an M-Pesa QR code for paying this amount to the Paybill with this account."""
    settings = get_settings()
    key = (settings.mpesa_shortcode, account, str(amount))
    if key in _qr_cache:
        _qr_cache.move_to_end(key)
        return _qr_cache[key]
    status, data = _post("/mpesa/qrcode/v1/generate", {
        "MerchantName": settings.mpesa_business_name or settings.app_name, "RefNo": account,
        "Amount": int(amount), "TrxCode": "PB", "CPI": settings.mpesa_shortcode, "Size": "300"})
    image = data.get("QRCode")
    if status != 200 or not image:
        raise DarajaError(data.get("errorMessage") or data.get("ResponseDescription") or f"HTTP {status}")
    _qr_cache[key] = image
    while len(_qr_cache) > 500:
        _qr_cache.popitem(last=False)
    return image


# ---- payments reported by Safaricom --------------------------------------------------------

def record_confirmation(db, payload: dict) -> C2BPayment | None:
    """Store one Paybill payment. Repeated notifications for the same TransID are ignored."""
    trans_id = str(payload.get("TransID") or "").strip().upper()
    if not trans_id:
        return None
    existing = db.scalar(select(C2BPayment).where(C2BPayment.trans_id == trans_id))
    if existing:
        return existing
    shortcode = str(payload.get("BusinessShortCode") or "")
    if shortcode and shortcode != get_settings().mpesa_shortcode:
        log.warning("Paybill payment %s for another shortcode %s ignored", trans_id, shortcode)
        return None
    names = " ".join(str(payload.get(k) or "").strip() for k in ("FirstName", "MiddleName", "LastName")
                     if payload.get(k) and str(payload.get(k)).lower() != "null")
    row = C2BPayment(trans_id=trans_id, trans_type=str(payload.get("TransactionType") or "")[:30] or None,
                     trans_time=str(payload.get("TransTime") or "")[:14] or None,
                     amount=Decimal(str(payload.get("TransAmount") or "0")),
                     account=clean_account(payload.get("BillRefNumber"))[:40] or None,
                     msisdn=str(payload.get("MSISDN") or "")[:30] or None, payer_name=names[:120] or None,
                     raw=payload, status="received")
    order, wash = match_account(db, row.account)
    if order is not None:
        row.order_id, row.branch_id = order.id, order.branch_id
    elif wash is not None:
        row.carwash_id, row.branch_id = wash.id, wash.branch_id
    db.add(row)
    db.flush()
    _confirm_waiting_entry(db, row)
    return row


def _confirm_waiting_entry(db, row: C2BPayment):
    """A cashier may have typed this receipt before Safaricom's notice arrived: confirm it now."""
    from .bill_lock import release_table
    from ..models import OrderStatusHistory
    payment = db.scalar(select(Payment).where(Payment.method == "m-pesa", Payment.status == "pending",
                                              func.upper(Payment.reference) == row.trans_id).execution_options(all_branches=True))
    if payment is not None and Decimal(payment.amount) == row.amount:
        now = datetime.utcnow()
        payment.status, payment.completed_at = "completed", now
        payment.notes = ((payment.notes or "") + " Confirmed by Safaricom's Paybill notice.").strip()
        order = payment.order
        order.status, order.cleared_at = "cleared", now
        order.version += 1
        release_table(db, order)
        db.add(OrderStatusHistory(order_id=order.id, status="cleared", changed_by=payment.recorded_by))
        row.status, row.payment_id, row.used_at, row.order_id, row.branch_id = "used", payment.id, now, order.id, order.branch_id
        return
    wash = db.scalar(select(CarWashTransaction).where(CarWashTransaction.payment_method == "m-pesa",
                                                      CarWashTransaction.payment_status == "pending",
                                                      func.upper(CarWashTransaction.mpesa_reference) == row.trans_id)
                     .execution_options(all_branches=True))
    if wash is not None and Decimal(wash.amount) == row.amount:
        now = datetime.utcnow()
        wash.payment_status, wash.completed_at = "completed", now
        row.status, row.used_at, row.carwash_id, row.branch_id = "used", now, wash.id, wash.branch_id


def claim(db, reference: str, amount, branch_id, order_id=None, carwash_id=None):
    """Use a Paybill payment Safaricom reported for a bill or wash.

    Returns the payment row if the receipt is one Safaricom reported (the caller can then
    mark the bill paid), or None if Safaricom has not reported it (the entry then waits
    for manual confirmation, as before). Raises when the receipt cannot be used.
    """
    trans_id = (reference or "").strip().upper()
    row = db.scalar(select(C2BPayment).where(C2BPayment.trans_id == trans_id).with_for_update()) if trans_id else None
    if row is None:
        return None
    if row.status == "used":
        raise HTTPException(409, f"M-Pesa payment {trans_id} was already used.")
    if row.amount != Decimal(str(amount)).quantize(Decimal("0.01")):
        raise HTTPException(400, f"M-Pesa payment {trans_id} is KES {row.amount:,.2f}, but this bill is KES {Decimal(str(amount)):,.2f}. "
                                 "Settle the difference separately.")
    if row.branch_id is not None and branch_id is not None and row.branch_id != branch_id:
        raise HTTPException(409, f"M-Pesa payment {trans_id} belongs to a bill at another branch.")
    row.status, row.used_at, row.branch_id = "used", datetime.utcnow(), branch_id
    row.order_id, row.carwash_id = order_id or row.order_id, carwash_id or row.carwash_id
    return row
