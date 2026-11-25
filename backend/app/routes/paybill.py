"""M-Pesa Paybill: details and QR code for a bill, payments Safaricom reported, and
the addresses Safaricom posts payments to (they must not contain "mpesa")."""
import hmac
import logging
from decimal import Decimal

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..branching import scope
from ..config import get_settings
from ..database import get_db
from ..middleware.auth import require_roles
from ..models import C2BPayment, CarWashTransaction, Order, User
from ..services import mpesa
from ..services.audit import record

router = APIRouter(prefix="/api/paybill", tags=["M-Pesa Paybill"])
callbacks = APIRouter(prefix="/api/c2b", include_in_schema=False)
bill_roles = require_roles("waiter", "cashier", "carwash_manager", "manager", "director")
money_roles = require_roles("cashier", "carwash_manager", "manager", "director")
log = logging.getLogger("biashara360.mpesa")


def out(row: C2BPayment):
    return {"id": row.id, "receipt": row.trans_id, "amount": row.amount, "account": row.account,
            "phone": row.msisdn, "payer": row.payer_name, "status": row.status, "order_id": row.order_id,
            "carwash_id": row.carwash_id, "received_at": row.received_at, "used_at": row.used_at}


def _visible(db, q):
    current = scope(db)
    if isinstance(current, int):
        # Payments with an unknown account number are shown to every branch, so the
        # cashier can find one by its receipt number.
        q = q.where(or_(C2BPayment.branch_id == current, C2BPayment.branch_id.is_(None)))
    return q


@router.get("/config")
def config(_=Depends(bill_roles)):
    settings = get_settings()
    return {"enabled": settings.mpesa_enabled, "paybill": settings.mpesa_shortcode or None,
            "environment": settings.mpesa_environment}


@router.get("/bill")
def bill_details(order_id: int | None = None, carwash_id: int | None = None, db: Session = Depends(get_db),
                 user: User = Depends(bill_roles)):
    """What to print on a bill: Paybill, account number, amount, QR code, and payments received."""
    if (order_id is None) == (carwash_id is None):
        raise HTTPException(422, "Give order_id or carwash_id")
    if order_id is not None:
        order = db.scalar(select(Order).where(Order.id == order_id))
        if not order or (user.role == "waiter" and order.waiter_id != user.id):
            raise HTTPException(404, "Bill not found")
        from ..services.payment_services import balance
        # A bill paid in parts shows what is still to pay.
        account, amount = mpesa.account_for(order=order), max(balance(db, order)[2], Decimal("0.00"))
        target = or_(C2BPayment.order_id == order.id, C2BPayment.account == account)
    else:
        wash = db.scalar(select(CarWashTransaction).where(CarWashTransaction.id == carwash_id))
        if not wash or user.role == "waiter":
            raise HTTPException(404, "Car wash not found")
        account, amount = mpesa.account_for(wash=wash), Decimal(wash.amount)
        target = or_(C2BPayment.carwash_id == wash.id, C2BPayment.account == account)
    settings = get_settings()
    result = {"paybill": settings.mpesa_shortcode or None, "account": account, "amount": amount,
              "qr": None, "qr_note": None, "payments": []}
    if not settings.mpesa_shortcode:
        result["qr_note"] = "No Paybill number is set up yet."
        return result
    result["payments"] = [out(r) for r in db.scalars(select(C2BPayment).where(target).order_by(C2BPayment.id.desc())).all()]
    if not settings.mpesa_enabled:
        result["qr_note"] = "QR codes appear once the Daraja keys are set up."
    elif amount != amount.to_integral_value():
        result["qr_note"] = "No QR code: M-Pesa QR codes need a whole-shilling amount."
    else:
        try:
            result["qr"] = mpesa.qr_code(account, amount)
        except (mpesa.DarajaError, httpx.HTTPError) as exc:
            log.warning("QR code not available: %s", exc)
            result["qr_note"] = "QR code unavailable right now. The customer can still pay by Paybill."
    return result


@router.get("/payments")
def payments(status: str | None = None, q: str | None = None, db: Session = Depends(get_db), _=Depends(money_roles)):
    """Payments into the Paybill, newest first. q finds a receipt or account number."""
    stmt = _visible(db, select(C2BPayment)).order_by(C2BPayment.id.desc()).limit(200)
    if status:
        stmt = stmt.where(C2BPayment.status == status)
    if q:
        key = mpesa.clean_account(q)
        stmt = stmt.where(or_(C2BPayment.trans_id == key, C2BPayment.account == key))
    return [out(r) for r in db.scalars(stmt).all()]


@router.post("/register")
def register(db: Session = Depends(get_db), user: User = Depends(require_roles("director"))):
    """Tell Safaricom where to send Paybill payments (once in production)."""
    if not mpesa.enabled():
        raise HTTPException(503, "Set the M-Pesa keys, Paybill number, public address and callback token first.")
    try:
        reply = mpesa.register_urls()
    except (mpesa.DarajaError, httpx.HTTPError) as exc:
        raise HTTPException(502, f"Safaricom did not accept the addresses: {exc}") from None
    record(db, user, "register_paybill_urls", "payments", 0, after={"reply": reply})
    db.commit()
    return {"registered": True, "reply": reply}


def _check(token: str):
    expected = get_settings().mpesa_callback_token
    if not expected or len(expected) < 16 or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(404, "Not Found")


@callbacks.post("/{token}/confirmation")
def confirmation(token: str, payload: dict = Body(...), db: Session = Depends(get_db)):
    _check(token)
    from ..services.bill_lock import start_write
    try:
        start_write(db)
        mpesa.record_confirmation(db, payload)
        db.commit()
    except Exception:
        db.rollback()
        log.exception("Paybill payment could not be stored: %s", payload.get("TransID"))
    return {"ResultCode": 0, "ResultDesc": "Success"}


@callbacks.post("/{token}/validation")
def validation(token: str, payload: dict = Body(...)):
    """Only called if Safaricom turns on validation for the Paybill. Every payment is accepted:
    a payment with an unknown account number is shown to staff to match by hand."""
    _check(token)
    return {"ResultCode": "0", "ResultDesc": "Accepted"}
