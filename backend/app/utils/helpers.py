from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from ..config import get_settings

def business_today():
    return datetime.now(ZoneInfo(get_settings().business_timezone)).date()

def date_window(day: date | None = None):
    day = day or business_today()
    zone = ZoneInfo(get_settings().business_timezone)
    start = datetime.combine(day, time.min, zone).astimezone(timezone.utc).replace(tzinfo=None)
    end = datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(timezone.utc).replace(tzinfo=None)
    return start, end

def money(value) -> float:
    return round(float(value or 0), 2)

def user_dict(u):
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role, "active": u.active, "department_id":u.department_id, "branch_id":u.branch_id}

def menu_dict(m):
    return {"id": m.id, "name": m.name, "price": money(m.price), "category_id": m.category_id,
            "category": m.category.name, "department_id": m.department_id, "department": m.department.name,
            "active": m.active, "image":m.image_url, "image_url":m.image_url,
            "description":m.description, "tax_rate":m.tax_rate, "price_includes_tax":True}

def order_dict(o):
    from .tax import order_tax
    from sqlalchemy.orm import object_session
    from sqlalchemy import select
    from ..models import Payment, KitchenLine, OrderItem
    from ..models.waiter import DiningTable, OrderBatch, BillChangeRequest
    db=object_session(o)
    table=db.get(DiningTable,o.table_id) if o.table_id else None
    batches=db.scalars(select(OrderBatch).where(OrderBatch.order_id==o.id).order_by(OrderBatch.created_at,OrderBatch.id)).all()
    changes=db.scalars(select(BillChangeRequest).where(BillChangeRequest.order_id==o.id).order_by(BillChangeRequest.id)).all()
    payment=db.scalar(select(Payment).where(Payment.order_id==o.id, Payment.status != 'rejected'))
    submissions=[{"id":b.id,"kind":b.kind,"items":b.items,"notes":b.notes,"created_at":b.created_at,
                  "deliveries":b.deliveries} for b in batches]
    # Legacy lines predate batches. Keep their original submission visible even after an addition.
    if not any(b.kind=="original" for b in batches):
        added={i["order_item_id"] for b in batches if b.kind=="addition" for i in b.items}
        original=[{"order_item_id":i.id,"menu_item_id":i.menu_item_id,"name":i.menu_item.name,
                   "quantity":i.quantity,"unit_price":money(i.price_at_time),"department_id":i.menu_item.department_id}
                  for i in o.items if i.id not in added]
        submissions.insert(0,{"id":"legacy-"+str(o.id),"kind":"original (legacy)","items":original,
                              "notes":o.notes,"created_at":o.created_at,"deliveries":[]})
    open_requests=[r for r in changes if r.status=="pending"]
    locked=payment is not None or o.status in {"cleared","completed","cancelled"}
    return {"id": o.id, "order_number": o.order_number, "waiter_id": o.waiter_id,
            "table_id":o.table_id,"table_number":table.number if table else None,"version":o.version,
            "tracked_kitchen":bool(db.scalar(select(KitchenLine.order_item_id).join(OrderItem, KitchenLine.order_item_id == OrderItem.id).where(OrderItem.order_id == o.id).limit(1))),
            "locked":locked,"payment_block_reason":"Resolve pending change requests before recording payment." if open_requests else None,
            "addition_block_reason":"This bill is locked." if locked else "Cancellation awaiting review." if any(r.kind=="cancel" for r in open_requests) else None,
            "batches":submissions,
            "change_requests":[{"id":r.id,"kind":r.kind,"items":r.items,"reason":r.reason,"status":r.status,
                                "decision_reason":r.decision_reason,"created_at":r.created_at,"decided_at":r.decided_at} for r in changes],
            "waiter": o.waiter.full_name or o.waiter.username, "customer": o.customer,
            "total": money(o.total), "tax_summary":order_tax(o), "status": o.status, "created_at": o.created_at,
            "cleared_at": o.cleared_at,
            "items": [{"id": i.id, "menu_item_id": i.menu_item_id, "name": i.name_at_time or i.menu_item.name,
                       "historical_name_known": i.name_at_time is not None,
                       "department": i.department_name_at_time or i.menu_item.department.name, "quantity": i.quantity-i.voided_quantity,
                       "submitted_quantity":i.quantity,"voided_quantity":i.voided_quantity,
                       "unit_price": money(i.price_at_time), "subtotal": money((i.quantity-i.voided_quantity)*i.price_at_time),
                       "tax_rate":i.tax_rate_at_time, "ready": i.ready} for i in o.items]}
