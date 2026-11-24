"""M-Pesa Express prompts: send, follow, stop, and Safaricom's callback."""
import hmac
import logging
from datetime import datetime, timedelta
from decimal import Decimal

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..middleware.auth import require_roles
from ..models import CarWashTransaction, MpesaRequest, Payment, User
from ..services import mpesa
from ..services.audit import record
from ..services.bill_lock import bill, pending, start_write

router = APIRouter(prefix="/api/mpesa", tags=["M-Pesa"])
staff = require_roles("cashier", "carwash_manager", "manager", "director")
managers = require_roles("manager", "director")
log = logging.getLogger("biashara360.mpesa")
# A new prompt for the same bill or wash is refused while the last one may still be answered.
PROMPT_WINDOW = timedelta(minutes=2)


class PromptIn(BaseModel):
    order_id: int | None = None
    carwash_id: int | None = None
    phone: str = Field(min_length=9, max_length=20)
    expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def one_target(self):
        if (self.order_id is None) == (self.carwash_id is None):
            raise ValueError("Give either order_id or carwash_id")
        return self


class ResolveIn(BaseModel):
    note: str = Field(min_length=3, max_length=500)


def masked(phone):
    return phone[:5] + "****" + phone[-3:] if phone and len(phone) > 8 else phone


def out(req: MpesaRequest):
    return {"id": req.id, "order_id": req.order_id, "carwash_id": req.carwash_id, "phone": masked(req.phone),
            "amount": req.amount, "status": req.status, "receipt": req.receipt, "message": mpesa.message(req),
            "result_code": req.result_code, "note": req.note, "created_at": req.created_at,
            "finished_at": req.finished_at}


@router.get("/config")
def config(_=Depends(staff)):
    settings = get_settings()
    return {"enabled": settings.mpesa_enabled, "environment": settings.mpesa_environment,
            "till": bool(settings.mpesa_till_number)}


@router.post("/prompts", status_code=201)
def send(data: PromptIn, db: Session = Depends(get_db), user: User = Depends(staff)):
    mpesa.require_enabled()
    phone = mpesa.normalize_phone(data.phone)
    start_write(db)
    if data.order_id is not None:
        if user.role == "carwash_manager":
            raise HTTPException(403, "Access denied")
        order = bill(db, data.order_id, user, data.expected_version)
        if order.table_id and data.expected_version is None:
            raise HTTPException(409, "Refresh this bill and submit its current version before requesting payment.")
        if order.status in ("cleared", "completed", "cancelled"):
            raise HTTPException(409, "This bill is already closed.")
        if db.scalar(select(Payment.id).where(Payment.order_id == order.id, Payment.status != "rejected")):
            raise HTTPException(409, "A payment is already recorded for this bill.")
        if pending(db, order.id):
            raise HTTPException(409, "Resolve pending change requests before requesting payment.")
        amount, target, reference = Decimal(order.total), MpesaRequest.order_id == order.id, order.order_number
    else:
        wash = db.scalar(select(CarWashTransaction).where(CarWashTransaction.id == data.carwash_id).with_for_update())
        if not wash:
            raise HTTPException(404, "Car wash not found")
        if wash.payment_method != "m-pesa" or wash.payment_status != "pending":
            raise HTTPException(409, "This car wash is not waiting for an M-Pesa payment.")
        amount, target, reference = Decimal(wash.amount), MpesaRequest.carwash_id == wash.id, wash.transaction_number
    if amount != amount.to_integral_value():
        raise HTTPException(400, "M-Pesa prompts need a whole-shilling amount. Record this payment by hand.")
    recent = db.scalar(select(MpesaRequest).where(target, MpesaRequest.status == "waiting",
                                                  MpesaRequest.created_at > datetime.utcnow() - PROMPT_WINDOW))
    if recent:
        raise HTTPException(409, "A prompt was sent less than 2 minutes ago and may still be answered. "
                                 "Wait for it, or stop it before sending another.")
    req = MpesaRequest(order_id=data.order_id, carwash_id=data.carwash_id, phone=phone, amount=amount,
                       status="waiting", created_by=user.id)
    db.add(req); db.flush()
    record(db, user, "mpesa_prompt", "mpesa", req.id, after={"amount": amount, "order_id": data.order_id,
                                                              "carwash_id": data.carwash_id})
    db.commit()
    # Call Safaricom without holding the bill lock.
    try:
        reply = mpesa.send_prompt(phone, amount, reference.replace("-", "")[-12:], "Biashara pay")
    except (mpesa.DarajaError, httpx.HTTPError) as exc:
        start_write(db)
        req = db.get(MpesaRequest, req.id)
        mpesa.mark_failed(db, req, "send", str(exc))
        db.commit()
        raise HTTPException(502, str(exc) if isinstance(exc, mpesa.DarajaError) else "M-Pesa could not be reached. Try again.")
    start_write(db)
    req = db.get(MpesaRequest, req.id)
    req.checkout_request_id = reply.get("CheckoutRequestID")
    req.merchant_request_id = reply.get("MerchantRequestID")
    db.commit()
    return out(req)


@router.get("/prompts")
def list_prompts(status: str | None = None, db: Session = Depends(get_db), _=Depends(managers)):
    q = select(MpesaRequest).order_by(MpesaRequest.id.desc()).limit(200)
    if status:
        q = q.where(MpesaRequest.status == status)
    return [out(r) for r in db.scalars(q).all()]


@router.get("/prompts/{prompt_id}")
def status(prompt_id: int, db: Session = Depends(get_db), _=Depends(staff)):
    req = db.get(MpesaRequest, prompt_id)
    if not req:
        raise HTTPException(404, "Prompt not found")
    if req.status == "waiting":
        start_write(db)
        req = db.scalar(select(MpesaRequest).where(MpesaRequest.id == prompt_id).with_for_update())
        mpesa.refresh(db, req)
        db.commit()
    return out(req)


@router.post("/prompts/{prompt_id}/stop")
def stop(prompt_id: int, db: Session = Depends(get_db), user: User = Depends(staff)):
    """Stop waiting (e.g. the customer pays cash instead). A payment that still arrives
    is applied if the bill or wash is unpaid, otherwise kept for a manager."""
    start_write(db)
    req = db.scalar(select(MpesaRequest).where(MpesaRequest.id == prompt_id).with_for_update())
    if not req:
        raise HTTPException(404, "Prompt not found")
    if req.status == "waiting":
        mpesa.mark_failed(db, req, "stopped", "Stopped by staff")
        record(db, user, "mpesa_prompt_stopped", "mpesa", req.id)
        db.commit()
    return out(req)


@router.post("/prompts/{prompt_id}/resolve")
def resolve(prompt_id: int, data: ResolveIn, db: Session = Depends(get_db), user: User = Depends(managers)):
    start_write(db)
    req = db.scalar(select(MpesaRequest).where(MpesaRequest.id == prompt_id).with_for_update())
    if not req:
        raise HTTPException(404, "Prompt not found")
    if req.status != "unmatched":
        raise HTTPException(409, "Only unmatched payments need resolving.")
    req.status, req.resolved_by = "resolved", user.id
    req.note = f"{req.note or ''} Resolved: {data.note.strip()}"[:500]
    record(db, user, "mpesa_unmatched_resolved", "mpesa", req.id, after={"note": data.note, "receipt": req.receipt})
    db.commit()
    return out(req)


@router.post("/callback/{token}", include_in_schema=False)
def callback(token: str, payload: dict = Body(...), db: Session = Depends(get_db)):
    expected = get_settings().mpesa_callback_token
    if not expected or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(404, "Not Found")
    try:
        start_write(db)
        mpesa.handle_callback(db, payload)
        db.commit()
    except Exception:
        db.rollback()
        # The status check (STK query) recovers the result later.
        log.exception("M-Pesa callback could not be processed")
    return {"ResultCode": 0, "ResultDesc": "Accepted"}
