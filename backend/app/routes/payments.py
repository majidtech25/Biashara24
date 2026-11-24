"""Records money received. Cash and Paybill payments Safaricom reported are confirmed at entry;
other cashless references are confirmed by staff."""
from datetime import date, datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..database import get_db
from ..middleware.auth import require_roles
from ..models import Order, OrderStatusHistory, Payment, User
from ..schemas import PaymentCreate
from ..utils.helpers import date_window, money, business_today
from ..services.payment_services import matches_order_total
from ..services.audit import record
from ..services.bill_lock import start_write, bill, pending, release_table
from ..services.transactions import begin_submission, finish_submission, reserve_receipt

router = APIRouter(prefix="/api", tags=["Payments"])
auth = require_roles("cashier", "manager", "director")

def out(p):
    from sqlalchemy.orm import object_session
    from ..models.waiter import DiningTable
    table=object_session(p).get(DiningTable,p.order.table_id) if p.order.table_id else None
    return {"id": p.id, "order_id": p.order_id, "order_number": p.order.order_number,
            "table_number":table.number if table else None,
            "amount": money(p.amount), "method": p.method, "status": p.status,
            "reference": p.reference, "reference_number": p.reference, "created_at": p.created_at,
            "completed_at": p.completed_at, "verified_by": p.verified_by,
            "receipt": f"RCP-{p.id:06d}" if p.status == 'completed' else None, "notes": p.notes,
            "rejection_reason": p.rejection_reason, "rejected_at": p.rejected_at,
            "snapshot": p.receipt_snapshot, "shift_id":p.shift_id,
            "tendered_amount":p.tendered_amount, "change_amount":p.change_amount}

@router.get("/payments")
def list_payments(day: date | None = None, method: str | None = None, status_filter: str | None = None,
                  from_date: date | None = None, to_date: date | None = None,
                  limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                  db: Session = Depends(get_db), _=Depends(auth)):
    q = select(Payment).order_by(Payment.created_at.desc(), Payment.id.desc())
    if day:
        start, end = date_window(day); q = q.where(Payment.created_at >= start, Payment.created_at < end)
    if from_date: q = q.where(Payment.created_at >= date_window(from_date)[0])
    if to_date: q = q.where(Payment.created_at < date_window(to_date)[1])
    if method: q = q.where(Payment.method == method)
    if status_filter: q = q.where(Payment.status == status_filter)
    return [out(p) for p in db.scalars(q.offset(offset).limit(limit)).all()]

@router.post("/orders/{order_id}/clear", status_code=201)
def clear_order(order_id: int, data: PaymentCreate, db: Session = Depends(get_db), user: User = Depends(auth),
                idempotency_key: str | None = Header(None, min_length=8, max_length=100)):
    start_write(db)
    submission, replay = begin_submission(db, user, idempotency_key, f'payment:{order_id}', data.model_dump())
    if replay is not None: return replay
    order = bill(db,order_id,user,data.expected_version)
    if order.table_id and data.expected_version is None:
        raise HTTPException(409,"Refresh this bill and submit its current version before recording payment.")
    if pending(db,order.id):
        raise HTTPException(409,"Resolve pending change requests before recording payment.")
    if order.status == "cancelled": raise HTTPException(409, "Cancelled orders cannot be paid")
    # A bill can be paid in parts (several people, or part cash and part M-Pesa). Each part
    # may be at most what is left; the part that pays the rest closes the bill.
    from ..services.payment_services import balance
    _, _, left = balance(db, order)
    if left <= 0:
        raise HTTPException(409, "A payment is already recorded for this order")
    amount_in = Decimal(str(data.amount)).quantize(Decimal("0.01"))
    if amount_in > left or (amount_in < left and not data.part_payment):
        raise HTTPException(400, f"Payment must equal order total of {order.total:.2f}" if left == Decimal(str(order.total)).quantize(Decimal("0.01"))
                            else f"KES {left:,.2f} is left to pay on this bill. Enter that amount, or mark this as a part payment.")
    final = amount_in == left
    reference = data.reference.upper().strip() if data.reference else None
    if data.method == "m-pesa" and not reference:
        raise HTTPException(400, "Enter the cashless receipt reference")
    # Cash is confirmed at entry. An M-Pesa receipt that Safaricom reported to the Paybill is
    # confirmed too; any other cashless reference awaits staff confirmation.
    from ..services.mpesa import claim
    paybill = claim(db, reference, data.amount, order.branch_id, order_id=order.id) if data.method == "m-pesa" else None
    completed = data.method == "cash" or paybill is not None
    is_cash = data.method == "cash"
    from ..services.cash_office import shift_for_payment
    from ..models import BusinessSettings
    shift = shift_for_payment(db, user)
    tendered = data.tendered_amount if data.tendered_amount is not None else data.amount
    if is_cash and tendered < data.amount: raise HTTPException(400, 'Cash tendered is less than the bill total.')
    business = db.get(BusinessSettings, 1)
    now = datetime.utcnow()
    from ..utils.helpers import order_dict
    from fastapi.encoders import jsonable_encoder
    snapshot = order_dict(order)
    # Only the payment that completes the bill holds active_order_id, so the database still
    # refuses two payments that each claim to finish the same bill.
    payment = Payment(order_id=order.id, active_order_id=order.id if final else None, amount=data.amount, method=data.method,
                      shift_id=shift.id if shift else None, recorded_by=user.id,
                      tendered_amount=tendered if is_cash else None, change_amount=money(tendered-data.amount) if is_cash else None,
                      receipt_snapshot=jsonable_encoder({k: snapshot[k] for k in ('order_number','table_number','waiter','items','tax_summary','total')} | {'business': business.values if business else {'business_name':'Biashara360'}}),
                      status="completed" if completed else "pending", reference=reference, notes=data.notes,
                      verified_by=user.id if completed else None, completed_at=now if completed else None)
    order.version += 1
    db.add(payment)
    try:
        db.flush()
        from ..services.payment_services import settle
        if not settle(db, order, user.id) and final and order.status != "payment_pending":
            order.status = "payment_pending"  # the rest is paid, waiting for a receipt to be confirmed
            db.add(OrderStatusHistory(order_id=order.id, status=order.status, changed_by=user.id))
        if data.method == 'm-pesa': reserve_receipt(db, reference, 'payment', payment.id)
        if paybill is not None: paybill.payment_id = payment.id
        record(db, user, "record", "payments", payment.id, after={"amount": payment.amount, "status": payment.status})
        finish_submission(submission, out(payment))
        db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409, "Payment already recorded")
    db.refresh(payment)
    return out(payment)


class PaymentRejection(BaseModel):
    reason: str = Field(min_length=3, max_length=500)

    @field_validator('reason')
    @classmethod
    def meaningful_reason(cls, value):
        if len(value.strip()) < 3: raise ValueError('Explain why this payment is being rejected.')
        return value.strip()


@router.post('/payments/{payment_id}/reject')
def reject(payment_id: int, data: PaymentRejection, db: Session = Depends(get_db),
           user: User = Depends(require_roles('manager', 'director'))):
    start_write(db)
    payment = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if not payment: raise HTTPException(404, 'Payment not found')
    if payment.status == 'rejected': return out(payment)
    if payment.status != 'pending': raise HTTPException(409, 'Only pending payments may be rejected. Confirmed payments require a refund.')
    order = bill(db, payment.order_id, user)
    payment.status = 'rejected'
    payment.active_order_id = None
    payment.rejected_at = datetime.utcnow()
    payment.rejected_by = user.id
    payment.rejection_reason = data.reason
    from ..models import ExternalReceipt
    reservation = db.get(ExternalReceipt, payment.reference)
    if reservation and reservation.source == 'payment' and reservation.source_id == payment.id:
        db.delete(reservation)
    if order.status == 'payment_pending':
        order.status = 'ready' if all(i.ready for i in order.items if i.quantity > i.voided_quantity) else 'pending'
        db.add(OrderStatusHistory(order_id=order.id, status=order.status, changed_by=user.id))
    order.version += 1
    record(db, user, 'reject', 'payments', payment.id, before={'status': 'pending'},
           after={'status': 'rejected', 'reason': data.reason, 'reference': payment.reference})
    db.commit()
    return out(payment)

@router.put("/payments/{payment_id}/verify")
def verify(payment_id: int, db: Session = Depends(get_db), user: User = Depends(auth)):
    start_write(db)
    payment = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if not payment: raise HTTPException(404, "Payment not found")
    if payment.method != "m-pesa": raise HTTPException(400, "Only cashless payments need manual verification")
    if payment.status == "completed": return out(payment)
    if payment.status != "pending" or not payment.reference: raise HTTPException(409, "Payment cannot be verified")
    from ..services.mpesa import claim
    paybill = claim(db, payment.reference, payment.amount, payment.order.branch_id, order_id=payment.order_id)
    if paybill is not None: paybill.payment_id = payment.id
    payment.status = "completed"; payment.completed_at = datetime.utcnow(); payment.verified_by = user.id
    payment.order.version += 1
    from ..services.payment_services import settle
    settle(db, payment.order, user.id)
    record(db, user, "manual_receipt_confirmation", "payments", payment.id,
           before={"status": "pending"}, after={"status": "completed", "reference": payment.reference})
    db.commit()
    return out(payment)

@router.get("/payments/daily-summary")
def daily_summary(day: date | None = None, date_value: date | None = Query(None, alias="date"),
                  db: Session = Depends(get_db), _=Depends(auth)):
    start, end = date_window(date_value or day)
    rows = db.execute(select(Payment.method, func.sum(Payment.amount), func.count(Payment.id)).where(
        Payment.status == "completed", Payment.completed_at >= start, Payment.completed_at < end).group_by(Payment.method)).all()
    values = {r[0]: {"amount": money(r[1]), "count": r[2]} for r in rows}
    cash = values.get("cash", {"amount": 0, "count": 0}); mpesa = values.get("m-pesa", {"amount": 0, "count": 0})
    total = money(cash["amount"] + mpesa["amount"])
    return {"date": date_value or day or business_today(), "cash": cash, "m_pesa": mpesa, "total": total,
            "orders": cash["count"] + mpesa["count"], "cash_count": cash["count"], "cash_total": cash["amount"],
            "mpesa_count": mpesa["count"], "mpesa_total": mpesa["amount"], "total_revenue": total,
            "orders_cleared": cash["count"] + mpesa["count"]}
