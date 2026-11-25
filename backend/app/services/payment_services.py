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
        use_ingredients(db, order, actor_id)
        return True
    return False


def use_ingredients(db, order, actor_id):
    """Take the dishes' ingredients off stock when the bill is paid (Majid, 2026-11-25).

    There is no kitchen screen, so nothing marks a dish as started. The ingredients held when the
    waiter sent the order are used up now; a cancelled order never reaches this point."""
    from datetime import datetime
    from ..models import KitchenLine, User
    from .production import start_preparation
    actor = db.get(User, actor_id)
    for item in order.items:
        state = db.get(KitchenLine, item.id)
        if not state or state.status in ('served', 'cancelled'):
            continue
        start_preparation(db, item, state, actor)  # uses whatever is still held for this dish
        state.status, state.served_at = 'served', datetime.utcnow()
        state.version += 1
