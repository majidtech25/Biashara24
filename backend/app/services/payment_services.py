"""Payment validation rules."""
from decimal import Decimal

def matches_order_total(amount: float, total: float) -> bool:
    return Decimal(str(amount)).quantize(Decimal("0.01")) == Decimal(str(total)).quantize(Decimal("0.01"))


def payments_for(db, order):
    """Payments recorded against a bill, not counting rejected ones."""
    from sqlalchemy import select
    from ..models import Payment
    return db.scalars(select(Payment).where(Payment.order_id == order.id, Payment.status != 'rejected').order_by(Payment.id)).all()


def balance(db, order):
    """(confirmed, waiting for confirmation, still to pay) for a bill. A bill may be paid in parts."""
    rows = payments_for(db, order)
    confirmed = sum((Decimal(str(p.amount)) for p in rows if p.status == 'completed'), Decimal('0.00'))
    waiting = sum((Decimal(str(p.amount)) for p in rows if p.status == 'pending'), Decimal('0.00'))
    return confirmed, waiting, Decimal(str(order.total)).quantize(Decimal('0.01')) - confirmed - waiting


def settle(db, order, actor_id):
    """Close the bill once confirmed payments cover it. Returns True when the bill was cleared."""
    from datetime import datetime
    from ..models import OrderStatusHistory
    from .bill_lock import release_table
    confirmed, waiting, left = balance(db, order)
    if left == 0 and waiting == 0 and order.status not in ('cleared', 'completed', 'cancelled'):
        order.status, order.cleared_at = 'cleared', datetime.utcnow()
        order.version += 1
        release_table(db, order)
        db.add(OrderStatusHistory(order_id=order.id, status='cleared', changed_by=actor_id))
        return True
    return False
