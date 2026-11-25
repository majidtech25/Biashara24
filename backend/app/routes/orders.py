from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..branching import scope,switched_off
from ..database import get_db
from ..middleware.auth import require_roles
from ..models import MenuItem, Order, OrderStatusHistory, User
from ..models.waiter import DiningTable, TableReservation, BillChangeRequest
from ..schemas import (OrderCreate, OrderUpdate, OrderAddition, ChangeCreate, ChangeDecision, TableCreate, TableUpdate, SplitBill)
from ..utils.helpers import date_window, order_dict, menu_dict
from ..services.order_services import can_transition
from ..services import bill_workflow as workflow
from ..services.bill_lock import start_write, bill, pending, CLOSED
from ..services.audit import record

router=APIRouter(prefix="/api", tags=["Orders"])
readers=require_roles("waiter","cashier","manager","director")
writers=require_roles("waiter","manager","director")
waiters=require_roles("waiter")  # only waiters send orders to the kitchen
managers=require_roles("manager","director")

@router.get("/menu")
def active_menu(search: str | None = None, db:Session=Depends(get_db), user:User=Depends(require_roles('waiter','cashier','manager','director','store_manager','kitchen'))):
    q=select(MenuItem).where(MenuItem.active.is_(True)).order_by(MenuItem.name)
    if search:q=q.where(MenuItem.name.ilike(f"%{search}%"))
    off=switched_off(db,scope(db))  # items this branch has switched off
    return [menu_dict(x) for x in db.scalars(q).all() if x.category.is_active and x.department.is_active and x.id not in off]

@router.get("/tables")
def tables(db:Session=Depends(get_db), user:User=Depends(readers)):
    rows=[]
    for table in db.scalars(select(DiningTable).order_by(DiningTable.number)).all():
        if not table.is_active and user.role not in {"manager","director"}:continue
        reservation=db.get(TableReservation,table.id)
        order=db.get(Order,reservation.order_id) if reservation else None
        visible=order and (user.role!="waiter" or order.waiter_id==user.id)
        rows.append({"id":table.id,"number":table.number,"is_active":table.is_active,"occupied":order is not None,
                     "owner":(order.waiter.full_name or order.waiter.username) if order else None,
                     "mine":bool(order and order.waiter_id==user.id),"order_id":order.id if visible else None})
    return rows

@router.post("/tables",status_code=201)
def create_table(data:TableCreate,db:Session=Depends(get_db),user:User=Depends(managers)):
    start_write(db)
    if db.scalar(select(DiningTable).where(DiningTable.number==data.number)):raise HTTPException(409,"Table number already exists")
    table=DiningTable(**data.model_dump());db.add(table);db.flush()
    record(db,user,"create","tables",table.id,after=data.model_dump());db.commit()
    return {"id":table.id,**data.model_dump()}

@router.put("/tables/{table_id}")
def update_table(table_id:int,data:TableUpdate,db:Session=Depends(get_db),user:User=Depends(managers)):
    start_write(db)
    table=db.scalar(select(DiningTable).where(DiningTable.id==table_id).with_for_update())
    if not table:raise HTTPException(404,"Table not found")
    if not data.is_active and db.get(TableReservation,table.id):raise HTTPException(409,"This table has an active bill")
    table.is_active=data.is_active;record(db,user,"update","tables",table.id,after=data.model_dump());db.commit()
    return {"id":table.id,"number":table.number,"is_active":table.is_active}

@router.get("/orders")
def list_orders(status:str|None=None,status_filter:str|None=None,waiter_id:int|None=None,day:date|None=None,
                active:bool|None=None,sort:Literal["oldest","newest"]="newest",limit:int=Query(100,ge=1,le=100),
                offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(readers)):
    q=select(Order)
    if status_filter or status:q=q.where(Order.status==(status_filter or status))
    if active is True:q=q.where(Order.status.notin_(CLOSED))
    if active is False:q=q.where(Order.status.in_(CLOSED))
    if day:
        start,end=date_window(day);q=q.where(Order.created_at>=start,Order.created_at<end)
    if user.role=="waiter":q=q.where(Order.waiter_id==user.id)
    elif waiter_id:q=q.where(Order.waiter_id==waiter_id)
    q=q.order_by(Order.created_at.asc(),Order.id.asc()) if sort=="oldest" else q.order_by(Order.created_at.desc(),Order.id.desc())
    return [order_dict(o) for o in db.scalars(q.offset(offset).limit(limit)).unique().all()]

@router.get("/waiter/pending-bills")
@router.get("/orders/waiter/pending-bills")
def pending_bills(db:Session=Depends(get_db),user:User=Depends(readers)):
    return list_orders(active=True,sort="oldest",limit=100,offset=0,db=db,user=user)

@router.get("/orders/{order_id}")
def get_order(order_id:int,db:Session=Depends(get_db),user:User=Depends(readers)):
    return order_dict(bill(db,order_id,user))

@router.post("/orders",status_code=201)
def create_order(data:OrderCreate,idempotency_key:str=Header(min_length=8,max_length=100),
                 db:Session=Depends(get_db),user:User=Depends(waiters)):
    start_write(db)
    order,submission=workflow.create(db,user,data,idempotency_key)
    workflow.deliver(db,order,submission)
    return order_dict(order)

@router.post("/orders/{order_id}/items",status_code=201)
def add_items(order_id:int,data:OrderAddition,idempotency_key:str=Header(min_length=8,max_length=100),
              db:Session=Depends(get_db),user:User=Depends(waiters)):
    start_write(db)
    order,submission=workflow.add(db,user,order_id,data,idempotency_key)
    workflow.deliver(db,order,submission)
    return order_dict(order)

@router.post("/orders/{order_id}/split",status_code=201)
def split_bill(order_id:int,data:SplitBill,db:Session=Depends(get_db),user:User=Depends(readers)):
    """Move items to a new bill. Returns both bills."""
    start_write(db)
    order,new=workflow.split(db,user,order_id,data)
    return {"original":order_dict(order),"new":order_dict(new)}

@router.post("/orders/{order_id}/change-requests",status_code=201)
def request_change(order_id:int,data:ChangeCreate,db:Session=Depends(get_db),user:User=Depends(writers)):
    start_write(db)
    request=workflow.request_change(db,user,order_id,data)
    return {"request_id":request.id,"order":order_dict(bill(db,order_id,user))}

@router.get("/order-change-requests")
def change_requests(status:Literal["pending","approved","rejected"]="pending",db:Session=Depends(get_db),user:User=Depends(managers)):
    requests=db.scalars(select(BillChangeRequest).where(BillChangeRequest.status==status).order_by(BillChangeRequest.created_at,BillChangeRequest.id)).all()
    result=[]
    for request in requests:
        order=db.get(Order,request.order_id);lines={i.id:i for i in order.items}
        reduction=sum(workflow.amount(lines[i["order_item_id"]].price_at_time)*i["quantity"] for i in request.items)
        result.append({"id":request.id,"kind":request.kind,"items":request.items,"reason":request.reason,
                       "status":request.status,"created_at":request.created_at,"decision_reason":request.decision_reason,
                       "resulting_total":(0 if request.kind=="cancel" else float(workflow.amount(order.total)-reduction)) if request.status=="pending" else order.total,
                       "order":order_dict(order)})
    return result

@router.put("/order-change-requests/{request_id}")
def decide_change(request_id:int,data:ChangeDecision,db:Session=Depends(get_db),user:User=Depends(managers)):
    start_write(db)
    order,submission=workflow.decide(db,user,request_id,data)
    workflow.deliver(db,order,submission)
    return order_dict(order)

@router.put("/orders/{order_id}")
def update_order(order_id:int,data:OrderUpdate,db:Session=Depends(get_db),user:User=Depends(managers)):
    start_write(db);order=bill(db,order_id,user)
    if not can_transition(order.status,data.status):raise HTTPException(409,"Invalid order transition")
    if pending(db,order.id):raise HTTPException(409,"Resolve pending change requests first")
    # No kitchen screen: managers move bills through the pipeline; ingredients come off stock at payment.
    from ..models import Payment
    payment=db.scalar(select(Payment).where(Payment.order_id==order.id, Payment.status != 'rejected'))
    from ..services.payment_services import balance
    if data.status in {"cleared","completed"} and (not payment or balance(db,order)[1:]!=(0,0)):
        raise HTTPException(409,"Confirm payment before clearing the order")
    if payment and data.status not in {"cleared","completed"}:raise HTTPException(409,"A recorded payment locks the bill")
    order.status=data.status;order.version+=1
    db.add(OrderStatusHistory(order_id=order.id,status=data.status,changed_by=user.id));db.commit()
    return order_dict(order)

@router.delete("/orders/{order_id}",status_code=204)
def cancel(order_id:int,db:Session=Depends(get_db),user:User=Depends(managers)):
    start_write(db);order=bill(db,order_id,user)
    request=workflow.request_change(db,user,order_id,ChangeCreate(expected_version=order.version,kind="cancel",reason="Manager cancellation"))
    start_write(db)
    order,submission=workflow.decide(db,user,request.id,ChangeDecision(expected_version=order.version,decision="approved",reason="Manager cancellation"))
    workflow.deliver(db,order,submission)
