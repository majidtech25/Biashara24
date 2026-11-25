"""Persisted restaurant operations. All posting runs in one database transaction."""
from datetime import date
from decimal import Decimal
from typing import Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from pydantic import Field, model_validator
from ..database import get_db
from ..middleware.auth import require_roles, current_user
from ..schemas import BaseModel
from ..models import (User, Order, OrderItem, Ingredient, Recipe, KitchenLine, Notification,
                      Supplier, StockDocument, FoodWaste, BusinessSettings, Department, DiningTable)
from ..models.user import now
from ..services.bill_lock import start_write, bill, pending
from ..services.audit import record
from ..services.transactions import begin_submission, finish_submission
from ..services.production import start_preparation, move, reserved

router = APIRouter(prefix='/api', tags=['Restaurant operations'])
management = require_roles('manager', 'director')
stock_auth = require_roles('store_manager', 'manager', 'director')
production_auth = require_roles('waiter', 'manager', 'director')


def fields(row, names):
    return {name: getattr(row, name) for name in names.split()}


class Component(BaseModel):
    ingredient_id: int = Field(gt=0)
    quantity: float = Field(gt=0, le=1000000, multiple_of=0.000001)


class RecipeInput(BaseModel):
    menu_item_id: int
    components: list[Component] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def unique_ingredients(self):
        if len({c.ingredient_id for c in self.components}) != len(self.components):
            raise ValueError('List each ingredient once.')
        return self


@router.get('/recipes')
def recipes(db: Session = Depends(get_db), _=Depends(stock_auth)):
    from ..models import MenuItem
    rows = db.scalars(select(Recipe).order_by(Recipe.id.desc())).all()
    return [fields(r, 'id menu_item_id version components created_at') | {'menu_name': db.get(MenuItem, r.menu_item_id).name} for r in rows]


@router.post('/recipes', status_code=201)
def save_recipe(data: RecipeInput, db: Session = Depends(get_db), user=Depends(stock_auth)):
    from ..models import MenuItem
    start_write(db)
    menu = db.scalar(select(MenuItem).where(MenuItem.id == data.menu_item_id).with_for_update())
    if not menu: raise HTTPException(404, 'Menu item not found')
    components = []
    for item in data.components:
        ingredient = db.get(Ingredient, item.ingredient_id)
        if not ingredient or not ingredient.is_active: raise HTTPException(400, 'Select active ingredients.')
        components.append(item.model_dump() | {'name': ingredient.name, 'unit': ingredient.unit, 'cost_per_unit': ingredient.cost_per_unit})
    version = (db.scalar(select(func.max(Recipe.version)).where(Recipe.menu_item_id == menu.id)) or 0) + 1
    row = Recipe(menu_item_id=menu.id, version=version, components=components, created_by=user.id)
    db.add(row); db.flush()
    record(db, user, 'recipe_version', 'recipes', row.id, after={'menu_item_id': menu.id, 'version': version, 'components': components})
    db.commit()
    return fields(row, 'id menu_item_id version components')


def kitchen_scope(query, user):
    if user.role == 'waiter': return query.where(Order.waiter_id == user.id)
    return query


@router.get('/kitchen/lines')
def kitchen_lines(department_id: int | None = None, db: Session = Depends(get_db), user=Depends(production_auth)):
    query = select(KitchenLine, OrderItem, Order).join(OrderItem, OrderItem.id == KitchenLine.order_item_id).join(Order, Order.id == OrderItem.order_id).where(KitchenLine.status.not_in(['served', 'cancelled']))
    if department_id: query = query.where(OrderItem.department_id_at_time == department_id)
    rows = db.execute(kitchen_scope(query, user).order_by(OrderItem.created_at).limit(500)).all()
    ids = {order.table_id for _, _, order in rows if order.table_id}
    tables = dict(db.execute(select(DiningTable.id, DiningTable.number).where(DiningTable.id.in_(ids))).all()) if ids else {}
    return [fields(state, 'order_item_id status version started_at ready_at served_at') | {
        'id': line.id, 'order_id': order.id, 'order_number': order.order_number,
        'name': line.name_at_time or line.menu_item.name, 'department': line.department_name_at_time,
        'quantity': line.quantity - line.voided_quantity, 'recipe_configured': bool(state.recipe_snapshot),
        'created_at': line.created_at, 'order_type': order.order_type, 'customer': order.customer, 'notes': order.notes,
        'table_number': tables.get(order.table_id), 'waiter': (order.waiter.full_name or order.waiter.username) if order.waiter else None}
        for state, line, order in rows]


class KitchenUpdate(BaseModel):
    status: Literal['preparing', 'ready', 'served']
    expected_version: int = Field(ge=1)


@router.put('/kitchen/lines/{line_id}')
def progress(line_id: int, data: KitchenUpdate, db: Session = Depends(get_db), user=Depends(production_auth)):
    start_write(db)
    query = select(OrderItem).join(Order, Order.id == OrderItem.order_id).where(OrderItem.id == line_id)
    line = db.scalar(kitchen_scope(query, user))
    if not line: raise HTTPException(404, 'Kitchen line not found')
    order = bill(db, line.order_id, user)
    if pending(db, order.id): raise HTTPException(409, 'Resolve pending bill changes before preparation continues.')
    state = db.scalar(select(KitchenLine).where(KitchenLine.order_item_id == line_id).with_for_update())
    if not state: raise HTTPException(409, 'Legacy line has no tracked preparation history.')
    if state.version != data.expected_version: raise HTTPException(409, 'Kitchen progress changed. Refresh first.')
    if user.role == 'waiter' and data.status != 'served': raise HTTPException(403, 'Waiters may mark ready food served.')
    if {'pending': 'preparing', 'preparing': 'ready', 'ready': 'served'}.get(state.status) != data.status:
        raise HTTPException(409, 'Invalid preparation transition.')
    before = state.status
    if data.status == 'preparing': start_preparation(db, line, state, user); state.started_at = now()
    if data.status == 'ready':
        state.ready_at = now(); line.ready = True
        db.add(Notification(user_id=order.waiter_id, order_id=order.id, message=f'{line.name_at_time or line.menu_item.name} is ready for {order.order_number}.'))
    if data.status == 'served': state.served_at = now()
    state.status = data.status; state.version += 1; order.version += 1
    db.flush()
    from ..models import OrderStatusHistory
    if order.status not in ('cleared','completed','cancelled','payment_pending'):
        states = db.scalars(select(KitchenLine).join(OrderItem, OrderItem.id == KitchenLine.order_item_id).where(OrderItem.order_id == order.id, KitchenLine.status != 'cancelled')).all()
        aggregate = 'pending' if any(s.status == 'pending' for s in states) else 'printed' if any(s.status == 'preparing' for s in states) else 'ready'
        if order.status != aggregate:
            order.status = aggregate
            db.add(OrderStatusHistory(order_id=order.id, status=aggregate, changed_by=user.id))
    record(db, user, 'progress', 'kitchen', line.id, before={'status': before}, after={'status': state.status})
    db.commit()
    return fields(state, 'order_item_id status version started_at ready_at served_at')


@router.get('/notifications')
def notifications(db: Session = Depends(get_db), user=Depends(current_user)):
    return [fields(r, 'id message order_id created_at read_at') for r in db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.id.desc()).limit(200))]


@router.put('/notifications/{identity}/read')
def read_notification(identity: int, db: Session = Depends(get_db), user=Depends(current_user)):
    row = db.get(Notification, identity)
    if not row or row.user_id != user.id: raise HTTPException(404, 'Notification not found')
    row.read_at = row.read_at or now(); db.commit()
    return fields(row, 'id message read_at')


class SupplierInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    contact: str = Field(default='', max_length=200)
    active: bool = True


@router.get('/suppliers')
def suppliers(db: Session = Depends(get_db), _=Depends(stock_auth)):
    return [fields(r, 'id name contact active') for r in db.scalars(select(Supplier).order_by(Supplier.name))]


@router.post('/suppliers', status_code=201)
def create_supplier(data: SupplierInput, db: Session = Depends(get_db), user=Depends(stock_auth)):
    row = Supplier(**data.model_dump()); db.add(row); db.flush()
    record(db, user, 'create', 'suppliers', row.id, after=data.model_dump()); db.commit()
    return fields(row, 'id name contact active')


class DocumentLine(BaseModel):
    ingredient_id: int = Field(gt=0)
    quantity: float = Field(ge=0, le=1000000)
    pack: str | None = Field(default=None, max_length=40)  # entered in this pack instead of the stock unit
    unit_cost: float | None = Field(default=None, ge=0, le=100000000)  # price per entered unit (deliveries)
    expiry_date: date | None = None  # deliveries only


class DocumentInput(BaseModel):
    kind: Literal['receiving', 'count', 'wastage', 'purchase', 'return']
    supplier_id: int | None = None
    reference: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=3, max_length=500)
    lines: list[DocumentLine] = Field(min_length=1, max_length=100)


def stock_line(ingredient, item, kind):
    """One document line in the ingredient's stock unit. Packs are converted, and the
    entered figures are kept on the line so the document reads as it was typed."""
    from ..services.production import quantity as exact
    factor = Decimal(1)
    if item.pack:
        pack = next((p for p in ingredient.packs if p.name.lower() == item.pack.strip().lower()), None)
        if not pack: raise HTTPException(400, f'{ingredient.name} has no pack called "{item.pack}".')
        factor = Decimal(pack.factor)
    if item.expiry_date and kind not in ('receiving', 'purchase'):
        raise HTTPException(400, 'Expiry dates are recorded on deliveries only.')
    if item.unit_cost is not None and kind not in ('receiving', 'purchase'):
        raise HTTPException(400, 'Prices are recorded on deliveries and purchases only.')
    line = {'ingredient_id': ingredient.id, 'quantity': exact(Decimal(str(item.quantity)) * factor),
            'name': ingredient.name, 'unit': ingredient.unit}
    if item.pack:
        line |= {'pack': pack.name, 'pack_quantity': item.quantity, 'factor': float(factor)}
    if item.unit_cost is not None:
        line['unit_cost'] = float((Decimal(str(item.unit_cost)) / factor).quantize(Decimal('0.0001')))
    if item.expiry_date:
        line['expiry_date'] = item.expiry_date.isoformat()
    return line


def receive_line(db, user, ingredient, line, reason, document_id):
    """Add delivered stock: update the ingredient's cost first, so the movement records it,
    and keep a batch when the delivery has an expiry date."""
    from ..models import StockBatch
    if line.get('unit_cost') is not None:
        ingredient.cost_per_unit = line['unit_cost']
    move(db, user, ingredient, line['quantity'], reason, 'receiving', document_id)
    if line.get('expiry_date') and line['quantity'] > 0:
        db.add(StockBatch(ingredient_id=ingredient.id, document_id=document_id, quantity=line['quantity'],
                          remaining=line['quantity'], expiry_date=date.fromisoformat(line['expiry_date'])))


def document_out(row):
    return fields(row, 'id kind supplier_id reference reason lines status created_by posted_by created_at posted_at')


@router.get('/stock/documents')
def documents(db: Session = Depends(get_db), _=Depends(stock_auth)):
    return [document_out(r) for r in db.scalars(select(StockDocument).order_by(StockDocument.id.desc()).limit(200))]


@router.post('/stock/documents', status_code=201)
def draft_document(data: DocumentInput, db: Session = Depends(get_db), user=Depends(stock_auth),
                   idempotency_key: str = Header(..., min_length=8, max_length=100)):
    start_write(db)
    submission, replay = begin_submission(db, user, idempotency_key, 'stock:document', data.model_dump(mode='json'))
    if replay is not None: return replay
    if len({i.ingredient_id for i in data.lines}) != len(data.lines): raise HTTPException(400, 'List each ingredient once.')
    if data.supplier_id:
        supplier = db.get(Supplier, data.supplier_id)
        if not supplier or not supplier.active: raise HTTPException(400, 'Select an active supplier.')
    if data.kind in ('purchase', 'return') and not data.supplier_id:
        raise HTTPException(400, 'Select the supplier for this ' + ('purchase order.' if data.kind == 'purchase' else 'return.'))
    entries = []
    for item in sorted(data.lines, key=lambda x: x.ingredient_id):
        ingredient = db.scalar(select(Ingredient).where(Ingredient.id == item.ingredient_id).with_for_update())
        if not ingredient or not ingredient.is_active: raise HTTPException(400, 'Select active ingredients.')
        entries.append(stock_line(ingredient, item, data.kind) | {'expected': ingredient.current_stock})
    row = StockDocument(**data.model_dump(exclude={'lines'}), lines=entries, created_by=user.id)
    db.add(row); db.flush()
    record(db, user, 'draft', 'stock_documents', row.id, after={'kind': row.kind, 'reference': row.reference})
    response = document_out(row); finish_submission(submission, response); db.commit()
    return response


@router.post('/stock/documents/{identity}/post')
def post_document(identity: int, db: Session = Depends(get_db), user=Depends(stock_auth)):
    start_write(db)
    row = db.scalar(select(StockDocument).where(StockDocument.id == identity).with_for_update())
    if not row: raise HTTPException(404, 'Stock document not found')
    if row.status == 'posted': return document_out(row)
    if row.kind == 'purchase':
        if user.role not in ('manager', 'director'): raise HTTPException(403, 'Management must approve purchases.')
        if row.status in ('approved', 'part_received', 'received'): return document_out(row)
        row.status = 'approved'; row.posted_by = user.id; row.posted_at = now()
        record(db, user, 'approve_purchase', 'stock_documents', row.id, after={'reference': row.reference})
        db.commit()
        return document_out(row)
    if row.kind == 'count' and (user.role not in ('manager', 'director') or user.id == row.created_by):
        raise HTTPException(403, 'A different manager or director must approve this count.')
    posted = []
    for item in row.lines:
        ingredient = db.scalar(select(Ingredient).where(Ingredient.id == item['ingredient_id']).with_for_update())
        if row.kind == 'count' and ingredient.current_stock != item['expected']:
            raise HTTPException(409, 'Stock moved after the count started. Recount before posting.')
        delta = item['quantity'] if row.kind == 'receiving' else -item['quantity'] if row.kind in ('wastage', 'return') else item['quantity'] - ingredient.current_stock
        before = ingredient.current_stock
        if row.kind == 'receiving':
            receive_line(db, user, ingredient, item, row.reason, row.id)
        else:
            move(db, user, ingredient, delta, row.reason, row.kind, row.id)
        posted.append(item | {'before': before, 'after': ingredient.current_stock, 'delta': delta})
    row.lines = posted; row.status = 'posted'; row.posted_by = user.id; row.posted_at = now()
    record(db, user, 'post', 'stock_documents', row.id, after={'lines': posted})
    db.commit()
    return document_out(row)


class ReceivedLine(DocumentLine):
    quantity: float = Field(gt=0, le=1000000)


class ReceivePurchase(BaseModel):
    reference: str = Field(min_length=1, max_length=100)
    lines: list[ReceivedLine] = Field(min_length=1, max_length=100)


@router.post('/stock/documents/{identity}/receive', status_code=201)
def receive_purchase(identity: int, data: ReceivePurchase, db: Session = Depends(get_db), user=Depends(stock_auth),
                     idempotency_key: str = Header(..., min_length=8, max_length=100)):
    start_write(db)
    submission, replay = begin_submission(db, user, idempotency_key, f'purchase:receive:{identity}', data.model_dump(mode='json'))
    if replay is not None: return replay
    purchase = db.scalar(select(StockDocument).where(StockDocument.id == identity).with_for_update())
    if not purchase or purchase.kind != 'purchase': raise HTTPException(404, 'Purchase order not found')
    if purchase.status not in ('approved', 'part_received'): raise HTTPException(409, 'Purchase must be approved and have outstanding quantities.')
    if len({i.ingredient_id for i in data.lines}) != len(data.lines): raise HTTPException(400, 'List each ingredient once.')
    if db.scalar(select(StockDocument.id).where(StockDocument.kind == 'receiving', StockDocument.supplier_id == purchase.supplier_id, StockDocument.reference == data.reference)):
        raise HTTPException(409, 'This supplier delivery reference is already recorded.')
    receipt = StockDocument(kind='receiving', supplier_id=purchase.supplier_id, reference=data.reference,
                            reason=f'Receipt against purchase {purchase.id}: {purchase.reference}', lines=[], status='posted',
                            created_by=user.id, posted_by=user.id, posted_at=now())
    db.add(receipt); db.flush()
    updated = [dict(i) for i in purchase.lines]; received = []
    for item in sorted(data.lines, key=lambda i: i.ingredient_id):
        planned = next((i for i in updated if i['ingredient_id'] == item.ingredient_id), None)
        ingredient = db.scalar(select(Ingredient).where(Ingredient.id == item.ingredient_id).with_for_update())
        if not planned or not ingredient: raise HTTPException(409, 'Received quantity exceeds the outstanding purchase quantity.')
        line = stock_line(ingredient, item, 'receiving')
        if 'unit_cost' not in line and planned.get('unit_cost') is not None:
            line['unit_cost'] = planned['unit_cost']  # the price agreed on the purchase order
        if line['quantity'] > planned['quantity'] - planned.get('received', 0) + 0.000001:
            raise HTTPException(409, 'Received quantity exceeds the outstanding purchase quantity.')
        before = ingredient.current_stock
        receive_line(db, user, ingredient, line, receipt.reason, receipt.id)
        from ..services.production import quantity
        planned['received'] = quantity(planned.get('received', 0) + line['quantity'])
        received.append(line | {'before': before, 'after': ingredient.current_stock, 'delta': line['quantity']})
    receipt.lines = received; purchase.lines = updated
    purchase.status = 'received' if all(i.get('received', 0) >= i['quantity'] for i in updated) else 'part_received'
    record(db, user, 'receive_purchase', 'stock_documents', purchase.id, after={'receipt_id': receipt.id, 'lines': received})
    result = document_out(receipt); finish_submission(submission, result); db.commit()
    return result


@router.get('/stock/food-waste')
def food_waste(db: Session = Depends(get_db), _=Depends(stock_auth)):
    return [fields(r, 'id order_item_id quantity reason ingredients created_at') for r in db.scalars(select(FoodWaste).order_by(FoodWaste.id.desc()).limit(200))]


DEFAULT_SETTINGS = {'business_name': 'Biashara360', 'address': '', 'phone': '', 'require_cashier_shift': False}


class SettingsInput(BaseModel):
    expected_version: int = Field(ge=0)
    business_name: str = Field(min_length=1, max_length=120)
    address: str = Field(default='', max_length=300)
    phone: str = Field(default='', max_length=40)
    require_cashier_shift: bool = False


@router.get('/settings')
def settings(db: Session = Depends(get_db), _=Depends(current_user)):
    row = db.get(BusinessSettings, 1)
    return {'version': row.version if row else 0, **(row.values if row else DEFAULT_SETTINGS)}


@router.put('/settings')
def save_settings(data: SettingsInput, db: Session = Depends(get_db), user=Depends(management)):
    start_write(db)
    row = db.scalar(select(BusinessSettings).where(BusinessSettings.id == 1).with_for_update())
    if data.expected_version != (row.version if row else 0): raise HTTPException(409, 'Settings changed. Refresh first.')
    before = row.values if row else DEFAULT_SETTINGS
    values = data.model_dump(exclude={'expected_version'})
    if row: row.values = values; row.version += 1
    else: row = BusinessSettings(id=1, version=1, values=values); db.add(row)
    record(db, user, 'update', 'settings', 1, before=before, after=values); db.commit()
    return {'version': row.version, **values}


@router.get('/printer-jobs')
def printer_jobs(db: Session = Depends(get_db), _=Depends(management)):
    from ..models import OrderBatch
    return [fields(row, 'id order_id kind created_at deliveries') for row in db.scalars(select(OrderBatch).order_by(OrderBatch.id.desc()).limit(200))]


class PrinterRetry(BaseModel):
    department_id: int
    reason: str = Field(min_length=3, max_length=500)
    acknowledge_duplicate_risk: Literal[True]


@router.post('/printer-jobs/{identity}/retry')
def retry_printer(identity: int, data: PrinterRetry, db: Session = Depends(get_db), user=Depends(management),
                  idempotency_key: str = Header(..., min_length=8, max_length=100)):
    from ..models import OrderBatch, DiningTable
    from ..services.printers_services import send_batch_ticket
    start_write(db)
    submission, replay = begin_submission(db, user, idempotency_key, f'printer:retry:{identity}', data.model_dump())
    if replay is not None: return replay
    batch = db.scalar(select(OrderBatch).where(OrderBatch.id == identity).with_for_update())
    if not batch: raise HTTPException(404, 'Printer job not found')
    deliveries = [dict(d) for d in batch.deliveries]
    index = next((i for i, d in enumerate(deliveries) if d['department_id'] == data.department_id), None)
    if index is None: raise HTTPException(404, 'Department is not on this ticket')
    department = db.get(Department, data.department_id)
    from ..services.printers_services import printer_for
    order = db.get(Order, batch.order_id)
    target = printer_for(db, department, order.branch_id) if department else None
    if not target: raise HTTPException(409, 'Configure the department printer first.')
    before = dict(deliveries[index])
    from .print_agents import agent_branch
    if agent_branch(db, order.branch_id):
        # The branch's print program collects it on its next check (within a few seconds).
        deliveries[index] = {**{k: v for k, v in before.items() if k != 'claim'}, 'status': 'queued', 'attempts': 0,
                             'last_retry_key': idempotency_key, 'retry_reason': data.reason}
        batch.deliveries = deliveries
        record(db, user, 'operator_reprint', 'printer_jobs', batch.id, before=before, after=deliveries[index])
        response = {'id': batch.id, 'department_id': data.department_id, 'status': 'queued'}
        finish_submission(submission, response); db.commit()
        return response
    deliveries[index] = {**before, 'status': 'uncertain', 'last_retry_key': idempotency_key, 'retry_reason': data.reason}
    batch.deliveries = deliveries
    record(db, user, 'operator_reprint', 'printer_jobs', batch.id, before=before, after=deliveries[index])
    response = {'id': batch.id, 'department_id': data.department_id, 'status': 'uncertain'}
    finish_submission(submission, response)
    db.commit()  # Durable claim BEFORE network I/O; replay never reprints.
    table = db.get(DiningTable, order.table_id) if order.table_id else None
    result = send_batch_ticket(department, order, batch, [i for i in batch.items if i['department_id'] == department.id], table.number if table else None, target)
    start_write(db)
    db.refresh(batch)
    deliveries = [dict(d) for d in batch.deliveries]
    # Do not overwrite a later explicitly authorised operator attempt.
    if deliveries[index].get('last_retry_key') == idempotency_key:
        deliveries[index].update(result); batch.deliveries = deliveries
    response.update(result); finish_submission(submission, response)
    record(db, user, 'reprint_result', 'printer_jobs', batch.id, after=response)
    db.commit()
    return response


class TransferInput(BaseModel):
    expected_version: int = Field(ge=1)
    table_id: int
    waiter_id: int
    reason: str = Field(min_length=3, max_length=500)


@router.post('/orders/{identity}/transfer')
def transfer(identity: int, data: TransferInput, db: Session = Depends(get_db), user=Depends(management)):
    from ..models import DiningTable, TableReservation
    from ..services.bill_lock import editable
    start_write(db)
    order = bill(db, identity, user, data.expected_version); editable(db, order)
    if pending(db, order.id): raise HTTPException(409, 'Resolve pending changes before transferring this bill.')
    table = db.scalar(select(DiningTable).where(DiningTable.id == data.table_id).with_for_update())
    waiter = db.get(User, data.waiter_id)
    if not table or not table.is_active or not waiter or not waiter.active or waiter.role != 'waiter':
        raise HTTPException(400, 'Select an active table and waiter.')
    reservation = db.get(TableReservation, table.id)
    if reservation and reservation.order_id != order.id: raise HTTPException(409, 'The destination table is occupied.')
    before = {'table_id': order.table_id, 'waiter_id': order.waiter_id}
    if order.table_id != table.id:
        old = db.scalar(select(TableReservation).where(TableReservation.order_id == order.id))
        if old: db.delete(old); db.flush()
        db.add(TableReservation(table_id=table.id, order_id=order.id))
    order.table_id = table.id; order.waiter_id = waiter.id; order.version += 1
    record(db, user, 'transfer', 'orders', order.id, before=before, after=data.model_dump())
    db.add(Notification(user_id=waiter.id, order_id=order.id, message=f'Bill {order.order_number} transferred to you at table {table.number}.'))
    db.commit()
    from ..utils.helpers import order_dict
    return order_dict(order)
