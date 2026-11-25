"""Transactional order additions, idempotency and reviewed corrections."""
import hashlib
import json
from ..database import _json_default
from decimal import Decimal, ROUND_HALF_UP
from fastapi import HTTPException
from sqlalchemy import select
from ..models import MenuItem, Order, OrderItem, OrderStatusHistory, Department, User
from ..models.waiter import DiningTable, TableReservation, OrderBatch, BillSubmission, BillChangeRequest
from ..models.user import now
from .audit import record
from .bill_lock import bill, editable, pending, release_table
from .order_services import new_order_number

def amount(value):
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def recalculate(order):
    order.total = (sum((amount(i.price_at_time) * (i.quantity-i.voided_quantity) for i in order.items), Decimal("0.00")))

def replay(db, user, key, operation, payload):
    digest = hashlib.sha256(json.dumps({"operation":operation,"payload":payload}, sort_keys=True, default=_json_default).encode()).hexdigest()
    prior = db.scalar(select(BillSubmission).where(BillSubmission.user_id == user.id, BillSubmission.key == key))
    if prior:
        if prior.fingerprint != digest:
            raise HTTPException(409, "This submission key was already used for different items. Start a new submission.")
        return digest, bill(db, prior.order_id, user)
    return digest, None

def batch(db, order, user, kind, entries, notes=None):
    deliveries = []
    for identity in sorted({i["department_id"] for i in entries}):
        department = db.get(Department, identity)
        deliveries.append({"department_id":identity, "department":department.name,
                           "status":"not_configured" if not department.printer_ip else "queued"})
    result = OrderBatch(order_id=order.id, kind=kind, items=entries, notes=notes, created_by=user.id,
                        deliveries=deliveries)
    db.add(result); db.flush()
    return result

def append_lines(db, order, lines):
    ids = {line.menu_item_id for line in lines}
    menu = {m.id:m for m in db.scalars(select(MenuItem).where(MenuItem.id.in_(ids))).all()}
    if len(menu) != len(ids) or any(not m.active or not m.category.is_active or not m.department.is_active for m in menu.values()):
        raise HTTPException(400, "One or more menu items are unavailable. Refresh the menu.")
    from ..branching import switched_off
    if ids & switched_off(db, order.branch_id):
        raise HTTPException(400, "One or more menu items are switched off at this branch. Refresh the menu.")
    entries = []
    for line in lines:
        item = menu[line.menu_item_id]
        entry = OrderItem(menu_item_id=item.id, quantity=line.quantity, price_at_time=amount(item.price), tax_rate_at_time=item.tax_rate, voided_quantity=0,
                          name_at_time=item.name, department_id_at_time=item.department_id,
                          department_name_at_time=item.department.name)
        order.items.append(entry); db.flush()
        from .production import reserve_line
        reserve_line(db, entry)
        entries.append({"order_item_id":entry.id,"menu_item_id":item.id,"name":item.name,"quantity":line.quantity,
                        "unit_price":float(amount(item.price)),"department_id":item.department_id,"department_name":item.department.name})
    recalculate(order)
    return entries

def create(db, user, data, key):
    fingerprint, previous = replay(db,user,key,"create",data.model_dump())
    if previous: return previous, None
    takeaway = data.order_type == "takeaway"
    table = None if takeaway else db.scalar(select(DiningTable).where(DiningTable.id == data.table_id).with_for_update())
    # A retry with the same key may have committed while this request waited for the lock
    # (PostgreSQL row locks; SQLite already serializes whole writes).
    fingerprint, previous = replay(db,user,key,"create",data.model_dump())
    if previous: return previous, None
    if not takeaway:
        if not table or not table.is_active: raise HTTPException(400, "Select an active table.")
        if db.get(TableReservation, table.id): raise HTTPException(409, "This table already has an active bill.")
    order = Order(order_number=new_order_number(), waiter_id=user.id, customer=data.customer, notes=data.notes,
                  table_id=table.id if table else None, order_type=data.order_type, version=1, total=0)
    db.add(order); db.flush()
    if table: db.add(TableReservation(table_id=table.id,order_id=order.id))
    entries = append_lines(db, order, data.items)
    submission = batch(db,order,user,"original",entries,data.notes)
    db.add(BillSubmission(user_id=user.id,key=key,fingerprint=fingerprint,order_id=order.id,batch_id=submission.id))
    db.add(OrderStatusHistory(order_id=order.id,status="pending",changed_by=user.id))
    record(db,user,"create_bill","orders",order.id,after={"table":table.number if table else "takeaway","batch_id":submission.id,"total":order.total})
    db.commit()
    return order, submission

def add(db, user, identity, data, key):
    fingerprint, previous = replay(db,user,key,"add:"+str(identity),data.model_dump())
    if previous: return previous, None
    bill(db,identity,user)  # lock the bill before checking the key again
    # A retry with the same key may have committed while this request waited for the lock.
    fingerprint, previous = replay(db,user,key,"add:"+str(identity),data.model_dump())
    if previous: return previous, None
    order = bill(db,identity,user,data.expected_version); editable(db,order)
    if any(r.kind == "cancel" for r in pending(db,identity)):
        raise HTTPException(409, "A cancellation request is awaiting review.")
    before = order.total
    entries = append_lines(db,order,data.items)
    submission = batch(db,order,user,"addition",entries,data.notes)
    order.version += 1
    order.status = "pending"
    db.add(BillSubmission(user_id=user.id,key=key,fingerprint=fingerprint,order_id=order.id,batch_id=submission.id))
    record(db,user,"add_items","orders",order.id,before={"total":before},after={"total":order.total,"batch_id":submission.id})
    db.commit()
    return order, submission

def request_change(db,user,identity,data):
    order = bill(db,identity,user,data.expected_version); editable(db,order)
    current = pending(db,identity)
    if any(r.kind == "cancel" for r in current) or (data.kind == "cancel" and current):
        raise HTTPException(409, "Resolve the existing request before requesting cancellation.")
    if data.kind == "cancel" and data.items: raise HTTPException(400, "Cancellation applies to the entire bill.")
    if data.kind == "remove":
        if not data.items: raise HTTPException(400, "Select items to remove.")
        ids=[line.order_item_id for line in data.items]
        if len(ids)!=len(set(ids)): raise HTTPException(400, "Select each item once.")
        occupied={entry["order_item_id"] for r in current for entry in r.items}
        available={line.id:line for line in order.items}
        for line in data.items:
            target=available.get(line.order_item_id)
            if not target or line.quantity > target.quantity-target.voided_quantity:
                raise HTTPException(400, "Removal exceeds the remaining item quantity.")
            if line.order_item_id in occupied: raise HTTPException(409, "This item already has a pending removal request.")
    request=BillChangeRequest(order_id=identity,kind=data.kind,items=[i.model_dump() for i in data.items],
                             reason=data.reason,requested_by=user.id)
    db.add(request);order.version+=1;db.flush()
    record(db,user,"request_"+data.kind,"orders",identity,after={"request_id":request.id,"reason":data.reason})
    db.commit()
    return request

def decide(db,user,identity,data):
    request = db.get(BillChangeRequest,identity)
    if not request: raise HTTPException(404,"Change request not found")
    order=bill(db,request.order_id,user,data.expected_version)
    db.refresh(request)
    if request.status!="pending": raise HTTPException(409,"This request has already been reviewed.")
    editable(db,order)
    submission=None;before=order.total
    if data.decision=="approved":
        targets={i.id:i for i in order.items}
        changes=request.items if request.kind=="remove" else [
            {"order_item_id":i.id,"quantity":i.quantity-i.voided_quantity} for i in order.items if i.quantity>i.voided_quantity]
        entries=[]
        for change in changes:
            line=targets.get(change["order_item_id"])
            if not line or change["quantity"]>line.quantity-line.voided_quantity:
                raise HTTPException(409,"The remaining quantity changed. Refresh the bill.")
            from .production import cancel_quantity
            cancel_quantity(db, line, change['quantity'], request.reason, user)
            line.voided_quantity+=change["quantity"]
            entries.append({"order_item_id":line.id,"menu_item_id":line.menu_item_id,"name":line.name_at_time or line.menu_item.name,
                            "quantity":-change["quantity"],"unit_price":line.price_at_time,"department_id":line.department_id_at_time or line.menu_item.department_id})
        recalculate(order)
        if request.kind=="cancel" or all(i.voided_quantity==i.quantity for i in order.items):
            order.status="cancelled";release_table(db,order)
            db.add(OrderStatusHistory(order_id=order.id,status="cancelled",changed_by=user.id))
        submission=batch(db,order,user,"correction",entries,request.reason)
    request.status=data.decision;request.decided_by=user.id;request.decision_reason=data.reason;request.decided_at=now()
    order.version+=1
    record(db,user,data.decision+"_"+request.kind,"orders",order.id,
           before={"total":before},after={"total":order.total,"request_id":request.id,"reason":data.reason})
    db.commit()
    return order,submission

def deliver(db,order,submission):
    if not submission: return
    from .printers_services import send_batch_ticket
    # Claim every destination before network I/O. Replays never call this function.
    for index, delivery in enumerate(submission.deliveries):
        if delivery["status"]!="queued": continue
        states=[dict(d) for d in submission.deliveries];states[index]["status"]="uncertain"
        submission.deliveries=states;db.commit()
        department=db.get(Department,delivery["department_id"])
        table=db.get(DiningTable,order.table_id) if order.table_id else None
        entries=[i for i in submission.items if i["department_id"]==department.id]
        result=send_batch_ticket(department,order,submission,entries,table.number if table else None)
        states=[dict(d) for d in submission.deliveries];states[index].update(result)
        submission.deliveries=states;db.commit()

def split(db, user, identity, data):
    """Move some items to a new bill, so people at one table can pay separately.
    Kitchen progress and reserved stock move with the items; nothing is printed again."""
    from ..models import KitchenLine, StockReservation
    order = bill(db, identity, user, data.expected_version); editable(db, order)
    if pending(db, identity): raise HTTPException(409, "Resolve pending change requests before splitting the bill.")
    ids = [line.order_item_id for line in data.items]
    if len(ids) != len(set(ids)): raise HTTPException(400, "Select each item once.")
    lines = {i.id: i for i in order.items}
    moving = {}
    for line in data.items:
        target = lines.get(line.order_item_id)
        if not target or line.quantity > target.quantity - target.voided_quantity:
            raise HTTPException(400, "The quantity to move is more than is left on the bill.")
        moving[target.id] = line.quantity
    if all(moving.get(i.id, 0) == i.quantity - i.voided_quantity for i in order.items if i.quantity > i.voided_quantity):
        raise HTTPException(400, "Leave at least one item on this bill.")
    new = Order(order_number=new_order_number(), waiter_id=order.waiter_id, customer=data.customer or order.customer,
                table_id=order.table_id, order_type=order.order_type, split_from_id=order.id, version=1, total=0,
                status=order.status, notes=f"Split from {order.order_number}", branch_id=order.branch_id)
    db.add(new); db.flush()
    entries = []
    for line_id, qty in moving.items():
        line = lines[line_id]
        state = db.get(KitchenLine, line.id)
        if qty == line.quantity - line.voided_quantity and line.voided_quantity == 0:
            line.order_id = new.id  # the whole line moves, with its kitchen state and reservations
            order.items.remove(line); new.items.append(line)
            moved = line
        else:
            moved = OrderItem(menu_item_id=line.menu_item_id, quantity=qty, voided_quantity=0, price_at_time=line.price_at_time,
                              tax_rate_at_time=line.tax_rate_at_time, name_at_time=line.name_at_time,
                              department_id_at_time=line.department_id_at_time, department_name_at_time=line.department_name_at_time,
                              ready=line.ready)
            new.items.append(moved); db.flush()
            line.quantity -= qty
            if state is not None:
                db.add(KitchenLine(order_item_id=moved.id, status=state.status, recipe_snapshot=state.recipe_snapshot,
                                   started_at=state.started_at, ready_at=state.ready_at, served_at=state.served_at))
                from .production import quantity
                for reservation in db.scalars(select(StockReservation).where(StockReservation.order_item_id == line.id)).all():
                    component = next(c for c in state.recipe_snapshot if c["ingredient_id"] == reservation.ingredient_id)
                    reservation.quantity = quantity(component["quantity"] * (line.quantity - line.voided_quantity))
                    db.add(StockReservation(order_item_id=moved.id, ingredient_id=reservation.ingredient_id,
                                            quantity=quantity(component["quantity"] * qty)))
                state.version += 1
        entries.append({"order_item_id": moved.id, "from_order_item_id": line_id, "menu_item_id": moved.menu_item_id,
                        "name": moved.name_at_time, "quantity": qty, "unit_price": float(moved.price_at_time),
                        "department_id": moved.department_id_at_time})
    db.flush()
    recalculate(order); recalculate(new)
    order.version += 1
    # History only: department deliveries are empty, so no ticket prints for the split.
    db.add(OrderBatch(order_id=new.id, kind="split", items=entries, notes=f"Split from {order.order_number}",
                      created_by=user.id, deliveries=[]))
    db.add(OrderStatusHistory(order_id=new.id, status=new.status, changed_by=user.id))
    record(db, user, "split_bill", "orders", order.id, after={"new_order_id": new.id, "items": entries,
                                                               "totals": [float(order.total), float(new.total)]})
    db.commit()
    return order, new
