from fastapi import HTTPException
from sqlalchemy import select, func
from ..models import CashShift, Payment, TillMovement, Refund, BusinessSettings, CarWashTransaction
from ..utils.helpers import money
from ..database import to_money


def shift_for_payment(db, user):
    row = db.scalar(select(CashShift).where(CashShift.active_cashier_id == user.id).with_for_update())
    settings = db.get(BusinessSettings, 1)
    if settings and settings.values.get('require_cashier_shift') and not row:
        raise HTTPException(409, 'Open your cashier shift before recording payments.')
    return row


def expected_cash(db, shift):
    receipts = db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.shift_id == shift.id, Payment.method == 'cash', Payment.status == 'completed'))
    movements = db.scalar(select(func.coalesce(func.sum(TillMovement.amount), 0)).where(TillMovement.shift_id == shift.id))
    refunds = db.scalar(select(func.coalesce(func.sum(Refund.amount), 0)).where(Refund.shift_id == shift.id))
    washes = db.scalar(select(func.coalesce(func.sum(CarWashTransaction.amount), 0)).where(CarWashTransaction.shift_id == shift.id, CarWashTransaction.payment_method == 'cash', CarWashTransaction.payment_status == 'completed'))
    return to_money(shift.opening_float + receipts + washes + movements - refunds)


def shift_out(db, shift):
    expected = shift.expected_cash if shift.status != 'open' else expected_cash(db, shift)
    return {k: getattr(shift, k) for k in ('id', 'cashier_id', 'status', 'opening_float', 'counted_cash', 'variance_reason', 'opened_at', 'closed_at', 'reviewed_by', 'reviewed_at')} | {
        'expected_cash': expected, 'variance': to_money(shift.counted_cash - expected) if shift.counted_cash is not None else None}
