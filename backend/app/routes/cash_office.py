from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from ..schemas import BaseModel, MoneyIn
from ..database import get_db
from ..middleware.auth import require_roles
from ..models import CashShift, TillMovement, Refund, Payment
from ..models.user import now
from ..services.bill_lock import start_write
from ..services.audit import record
from ..services.transactions import begin_submission, finish_submission
from ..services.cash_office import shift_out, expected_cash
from ..utils.helpers import money

router = APIRouter(prefix='/api', tags=['Cash office'])
cashier = require_roles('cashier', 'manager', 'director')
supervisor = require_roles('manager', 'director')


class OpenShift(BaseModel):
    opening_float: MoneyIn = Field(ge=0)


class CloseShift(BaseModel):
    counted_cash: MoneyIn = Field(ge=0)
    reason: str = Field(default='', max_length=500)


class Movement(BaseModel):
    amount: MoneyIn
    reason: str = Field(min_length=3, max_length=500)


class RefundInput(BaseModel):
    amount: MoneyIn = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)
    shift_id: int | None = None
    reference: str | None = Field(default=None, max_length=100)


@router.get('/cashier/shifts')
def shifts(db: Session = Depends(get_db), user=Depends(cashier)):
    query = select(CashShift).order_by(CashShift.id.desc()).limit(100)
    if user.role == 'cashier': query = query.where(CashShift.cashier_id == user.id)
    return [shift_out(db, row) for row in db.scalars(query)]


@router.post('/cashier/shifts', status_code=201)
def open_shift(data: OpenShift, db: Session = Depends(get_db), user=Depends(cashier),
               idempotency_key: str = Header(..., min_length=8, max_length=100)):
    start_write(db)
    submission, replay = begin_submission(db, user, idempotency_key, 'shift:open', data.model_dump())
    if replay is not None: return replay
    if db.scalar(select(CashShift).where(CashShift.active_cashier_id == user.id)):
        raise HTTPException(409, 'Close your current shift before opening another.')
    row = CashShift(cashier_id=user.id, active_cashier_id=user.id, opening_float=data.opening_float)
    db.add(row); db.flush()
    record(db, user, 'open', 'shifts', row.id, after=data.model_dump())
    response = shift_out(db, row); finish_submission(submission, response); db.commit()
    return response


def owned_shift(db, identity, user):
    row = db.scalar(select(CashShift).where(CashShift.id == identity).with_for_update())
    if not row or (user.role == 'cashier' and row.cashier_id != user.id): raise HTTPException(404, 'Shift not found')
    return row


@router.post('/cashier/shifts/{identity}/movements', status_code=201)
def movement(identity: int, data: Movement, db: Session = Depends(get_db), user=Depends(supervisor),
             idempotency_key: str = Header(..., min_length=8, max_length=100)):
    start_write(db)
    submission, replay = begin_submission(db, user, idempotency_key, f'shift:movement:{identity}', data.model_dump())
    if replay is not None: return replay
    row = owned_shift(db, identity, user)
    if row.status != 'open': raise HTTPException(409, 'This shift is closed.')
    if data.amount == 0 or expected_cash(db, row) + data.amount < 0: raise HTTPException(400, 'Enter a nonzero movement within the drawer balance.')
    entry = TillMovement(shift_id=row.id, recorded_by=user.id, **data.model_dump()); db.add(entry); db.flush()
    record(db, user, 'movement', 'shifts', row.id, after=data.model_dump())
    response = shift_out(db, row); finish_submission(submission, response); db.commit()
    return response


@router.post('/cashier/shifts/{identity}/close')
def close_shift(identity: int, data: CloseShift, db: Session = Depends(get_db), user=Depends(cashier)):
    start_write(db)
    row = owned_shift(db, identity, user)
    if row.status != 'open':
        if row.counted_cash != data.counted_cash or row.variance_reason != data.reason:
            raise HTTPException(409, 'This shift was already closed with different figures.')
        return shift_out(db, row)
    expected = expected_cash(db, row)
    if money(data.counted_cash - expected) != 0 and len(data.reason.strip()) < 3:
        raise HTTPException(400, 'Explain the cash variance before closing.')
    row.expected_cash = expected; row.counted_cash = data.counted_cash; row.variance_reason = data.reason
    row.status = 'awaiting_review'; row.active_cashier_id = None; row.closed_at = now()
    record(db, user, 'close', 'shifts', row.id, after={'expected_cash': expected, **data.model_dump()}); db.commit()
    return shift_out(db, row)


@router.post('/cashier/shifts/{identity}/review')
def review_shift(identity: int, db: Session = Depends(get_db), user=Depends(supervisor)):
    start_write(db)
    row = owned_shift(db, identity, user)
    if row.cashier_id == user.id: raise HTTPException(403, 'A different supervisor must review this shift.')
    if row.status == 'reviewed': return shift_out(db, row)
    if row.status != 'awaiting_review': raise HTTPException(409, 'Close the shift before review.')
    row.status = 'reviewed'; row.reviewed_by = user.id; row.reviewed_at = now()
    record(db, user, 'review', 'shifts', row.id, after={'variance': money(row.counted_cash - row.expected_cash)}); db.commit()
    return shift_out(db, row)


@router.get('/refunds')
def refunds(db: Session = Depends(get_db), _=Depends(cashier)):
    return [{'id': r.id, 'payment_id': r.payment_id, 'amount': r.amount, 'reason': r.reason, 'reference': r.reference,
             'credit_note': f'CRN-{r.id:06d}', 'created_at': r.created_at} for r in db.scalars(select(Refund).order_by(Refund.id.desc()).limit(200))]


@router.post('/payments/{identity}/refund', status_code=201)
def refund(identity: int, data: RefundInput, db: Session = Depends(get_db), user=Depends(supervisor),
           idempotency_key: str = Header(..., min_length=8, max_length=100)):
    start_write(db)
    submission, replay = begin_submission(db, user, idempotency_key, f'payment:refund:{identity}', data.model_dump())
    if replay is not None: return replay
    payment = db.scalar(select(Payment).where(Payment.id == identity).with_for_update())
    if not payment or payment.status != 'completed': raise HTTPException(409, 'Only confirmed payments may be refunded.')
    previous = db.scalar(select(func.coalesce(func.sum(Refund.amount), 0)).where(Refund.payment_id == payment.id))
    if money(previous + data.amount) > money(payment.amount): raise HTTPException(409, 'Refund exceeds the unrefunded payment amount.')
    shift_id = None
    if payment.method == 'cash':
        if not data.shift_id: raise HTTPException(400, 'Select the open drawer paying this cash refund.')
        shift = owned_shift(db, data.shift_id, user)
        if shift.status != 'open' or expected_cash(db, shift) < data.amount: raise HTTPException(409, 'The selected drawer is closed or has insufficient cash.')
        shift_id = shift.id
    elif not data.reference or not data.reference.strip(): raise HTTPException(400, 'Record the external refund reference.')
    reference = data.reference.strip().upper() if data.reference else None
    if reference and db.scalar(select(Refund.id).where(Refund.reference == reference)): raise HTTPException(409, 'Refund reference already recorded.')
    row = Refund(payment_id=payment.id, shift_id=shift_id, amount=data.amount, reason=data.reason, reference=reference, recorded_by=user.id)
    db.add(row); db.flush()
    record(db, user, 'refund', 'payments', payment.id, after={'refund_id': row.id, **data.model_dump()})
    response = {'id': row.id, 'payment_id': payment.id, 'amount': row.amount, 'credit_note': f'CRN-{row.id:06d}', 'reason': row.reason}
    finish_submission(submission, response); db.commit()
    return response
