from datetime import date, datetime
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database import get_db
from ..middleware.auth import require_roles
from ..models import CarWashTransaction, CarWashBay, CarWashService, CarWashAttendant, User
from ..models.user import now
from ..schemas import (CarWashCreate, BayCreate, WashServiceCreate, BayUpdate, WashServiceUpdate,
                       AttendantCreate, AttendantUpdate, WashProgress)
from ..utils.helpers import date_window, money, business_today
from ..services.audit import record
from ..services.bill_lock import start_write
from ..services.transactions import begin_submission, finish_submission, reserve_receipt

router = APIRouter(prefix="/api/carwash", tags=["Car wash"])
auth = require_roles("carwash_manager", "cashier", "manager", "director")
config_auth = require_roles("carwash_manager", "manager", "director")

def out(x):
    return {k: getattr(x, k) for k in ("id", "transaction_number", "bay_id", "service_id", "vehicle_plate",
            "vehicle_type", "payment_method", "amount", "payment_status", "mpesa_reference", "notes",
            "created_at", "started_at", "completed_at", "wash_status", "attendant_id", "wash_started_at",
            "wash_finished_at")} | {"recorded_by": x.created_by, "service_name": x.service_name_at_time}

ACTIVE_WASH = ("waiting", "washing")


def bay_out(x):
    return {"id": x.id, "bay_number": x.bay_number, "name": x.name, "is_active": x.is_active}


def service_out(x):
    return {"id": x.id, "name": x.name, "price": x.price, "description": x.description,
            "duration_minutes": x.duration_minutes, "is_active": x.is_active}


def attendant_out(x):
    return {"id": x.id, "name": x.name, "phone": x.phone, "is_active": x.is_active}


def busy_wash(db, bay_id, exclude=None):
    q = select(CarWashTransaction).where(CarWashTransaction.bay_id == bay_id,
                                         CarWashTransaction.wash_status.in_(ACTIVE_WASH))
    if exclude:
        q = q.where(CarWashTransaction.id != exclude)
    return db.scalar(q.limit(1))


def active_attendant(db, identity):
    attendant = db.get(CarWashAttendant, identity) if identity else None
    if not attendant or not attendant.is_active:
        raise HTTPException(400, "Select an active attendant")
    return attendant

def totals(rows):
    paid = [x for x in rows if x.payment_status == "completed"]
    cash = money(sum(x.amount for x in paid if x.payment_method == "cash"))
    mpesa = money(sum(x.amount for x in paid if x.payment_method == "m-pesa"))
    return {"total_washes": len(rows), "cash_total": cash, "mpesa_total": mpesa, "total_revenue": money(cash + mpesa)}

@router.get("/bays")
def bays(db: Session = Depends(get_db), _=Depends(auth)):
    return [bay_out(x) for x in db.scalars(select(CarWashBay).order_by(CarWashBay.bay_number)).all()]

@router.post("/bays", status_code=201)
def create_bay(data: BayCreate, db: Session = Depends(get_db), _=Depends(config_auth)):
    if db.scalar(select(CarWashBay).where(CarWashBay.bay_number == data.bay_number)): raise HTTPException(409, "Bay number already exists")
    x = CarWashBay(**data.model_dump()); db.add(x); db.commit(); db.refresh(x)
    return {"id": x.id, **data.model_dump()}

@router.get("/services")
def services(db: Session = Depends(get_db), _=Depends(auth)):
    return [service_out(x) for x in db.scalars(select(CarWashService).order_by(CarWashService.name)).all()]

@router.post("/services", status_code=201)
def create_service(data: WashServiceCreate, db: Session = Depends(get_db), _=Depends(config_auth)):
    if db.scalar(select(CarWashService).where(CarWashService.name == data.name)): raise HTTPException(409, "Service already exists")
    x = CarWashService(**data.model_dump()); db.add(x); db.commit(); db.refresh(x)
    return {"id": x.id, **data.model_dump()}

@router.post("/transaction", status_code=201)
def create(data: CarWashCreate, db: Session = Depends(get_db), user: User = Depends(auth),
           idempotency_key: str | None = Header(None, min_length=8, max_length=100)):
    start_write(db)
    submission, replay = begin_submission(db, user, idempotency_key, 'carwash:create', data.model_dump())
    if replay is not None: return replay
    for model, identity in ((CarWashBay, data.bay_id), (CarWashService, data.service_id)):
        item = db.get(model, identity) if identity else None
        if not item or not item.is_active: raise HTTPException(400, "Select an active bay and service")
    service = db.get(CarWashService, data.service_id)
    from ..services.cash_office import shift_for_payment
    shift = shift_for_payment(db, user)
    if money(data.amount) != money(service.price): raise HTTPException(400, "Amount must match the service price")
    if data.payment_method == "m-pesa" and not data.mpesa_reference and not data.mpesa_prompt: raise HTTPException(400, "Cashless receipt reference is required")
    if busy_wash(db, data.bay_id): raise HTTPException(409, "This bay already has a car. Finish that wash or choose another bay.")
    if data.attendant_id: active_attendant(db, data.attendant_id)
    values = data.model_dump(exclude={"mpesa_prompt"})
    values["wash_status"] = "waiting"
    # A cashless entry awaits manual confirmation against the external receipt.
    if data.payment_method == "m-pesa": values["payment_status"] = "pending"
    else: values['payment_status'] = 'completed'
    x = CarWashTransaction(**values, transaction_number="CW-" + uuid4().hex[:12].upper(),
          shift_id=shift.id if shift else None, service_name_at_time=service.name,
          created_by=user.id, completed_at=datetime.utcnow() if values["payment_status"] == "completed" else None)
    db.add(x); db.flush()
    if data.payment_method == 'm-pesa' and data.mpesa_reference: x.mpesa_reference = reserve_receipt(db, data.mpesa_reference, 'carwash', x.id)
    record(db, user, "create", "carwash", x.id, after={"amount": x.amount, "payment_status": x.payment_status})
    finish_submission(submission, out(x))
    db.commit(); db.refresh(x)
    return out(x)

@router.get("/today")
def today(db: Session = Depends(get_db), _=Depends(auth)):
    start, end = date_window()
    rows = db.scalars(select(CarWashTransaction).where(CarWashTransaction.created_at >= start, CarWashTransaction.created_at < end)
                      .order_by(CarWashTransaction.id.desc())).all()
    confirmed = db.scalars(select(CarWashTransaction).where(CarWashTransaction.completed_at >= start, CarWashTransaction.completed_at < end)).all()
    summary = totals(confirmed) | {"total_washes": len(rows)}
    return {"date": business_today(), "transactions": [out(x) for x in rows], "summary": summary}

@router.get("/history")
def history(from_date: date | None = None, to_date: date | None = None,
            start_date: date | None = None, end_date: date | None = None,
            payment_method: str | None = None, payment_status: str | None = None,
            limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
            db: Session = Depends(get_db), _=Depends(auth)):
    q = select(CarWashTransaction).order_by(CarWashTransaction.id.desc())
    first, last = from_date or start_date, to_date or end_date
    if first and last and first > last: raise HTTPException(400, "Start date must precede end date")
    if first: q = q.where(CarWashTransaction.created_at >= date_window(first)[0])
    if last: q = q.where(CarWashTransaction.created_at < date_window(last)[1])
    if payment_method: q = q.where(CarWashTransaction.payment_method == payment_method)
    if payment_status: q = q.where(CarWashTransaction.payment_status == payment_status)
    rows = db.scalars(q).all()
    return {"transactions": [out(x) for x in rows[offset:offset+limit]], "total": len(rows), "summary": totals(rows)}

class ManualConfirm(BaseModel):
    mpesa_reference: str | None = Field(default=None, max_length=100)


@router.post("/{transaction_id}/complete")
def complete(transaction_id: int, data: ManualConfirm | None = None, db: Session = Depends(get_db), user: User = Depends(auth)):
    start_write(db)
    x = db.scalar(select(CarWashTransaction).where(CarWashTransaction.id == transaction_id).with_for_update())
    if not x: raise HTTPException(404, "Transaction not found")
    if x.payment_status == "completed": return out(x)
    if x.payment_status != "pending": raise HTTPException(409, "Transaction cannot be confirmed")
    if x.payment_method == 'cash':
        from ..services.cash_office import shift_for_payment
        shift = shift_for_payment(db, user)
        x.shift_id = shift.id if shift else None
    if x.payment_method == "m-pesa" and not x.mpesa_reference:
        # Sent as a prompt that never completed: the customer paid another way.
        if not data or not data.mpesa_reference: raise HTTPException(400, "Enter the M-Pesa receipt number from the customer's message.")
        x.mpesa_reference = reserve_receipt(db, data.mpesa_reference, "carwash", x.id)
    x.payment_status = "completed"; x.completed_at = datetime.utcnow()
    record(db, user, "manual_payment_confirmation", "carwash", x.id, after={"status": "completed"})
    db.commit()
    return out(x)

@router.get("/daily-summary")
def summary(day: date | None = None, db: Session = Depends(get_db), _=Depends(auth)):
    start, end = date_window(day)
    rows = db.scalars(select(CarWashTransaction).where(CarWashTransaction.completed_at >= start, CarWashTransaction.completed_at < end)).all()
    return {"date": day or business_today(), **totals(rows)}



@router.put("/{transaction_id}/wash")
def progress(transaction_id: int, data: WashProgress, db: Session = Depends(get_db), user: User = Depends(auth)):
    """Move a wash forward: waiting -> washing (with an attendant) -> done. Payment is separate."""
    start_write(db)
    x = db.scalar(select(CarWashTransaction).where(CarWashTransaction.id == transaction_id).with_for_update())
    if not x: raise HTTPException(404, "Transaction not found")
    if x.wash_status == data.status: return out(x)  # a repeated tap changes nothing
    before = {"wash_status": x.wash_status, "attendant_id": x.attendant_id}
    if data.status == "washing":
        if x.wash_status != "waiting": raise HTTPException(409, "Only a waiting car can start washing")
        attendant = active_attendant(db, data.attendant_id or x.attendant_id)
        x.attendant_id = attendant.id; x.wash_started_at = now()
    else:
        if x.wash_status != "washing": raise HTTPException(409, "Start the wash before finishing it")
        x.wash_finished_at = now()
    x.wash_status = data.status
    record(db, user, "wash_" + data.status, "carwash", x.id, before=before,
           after={"wash_status": x.wash_status, "attendant_id": x.attendant_id})
    db.commit()
    return out(x)


@router.get("/board")
def board(db: Session = Depends(get_db), _=Depends(auth)):
    """Every active bay with the car currently on it, if any."""
    names = {a.id: a.name for a in db.scalars(select(CarWashAttendant)).all()}
    active = db.scalars(select(CarWashTransaction).where(CarWashTransaction.wash_status.in_(ACTIVE_WASH))
                        .order_by(CarWashTransaction.created_at)).all()
    by_bay = {}
    for wash in active:
        by_bay.setdefault(wash.bay_id, wash)
    result = []
    for bay in db.scalars(select(CarWashBay).where(CarWashBay.is_active.is_(True)).order_by(CarWashBay.bay_number)).all():
        wash = by_bay.get(bay.id)
        result.append(bay_out(bay) | {"status": "free" if not wash else wash.wash_status,
                                       "wash": (out(wash) | {"attendant": names.get(wash.attendant_id)}) if wash else None})
    return result


@router.put("/bays/{bay_id}")
def update_bay(bay_id: int, data: BayUpdate, db: Session = Depends(get_db), user: User = Depends(config_auth)):
    x = db.get(CarWashBay, bay_id)
    if not x: raise HTTPException(404, "Bay not found")
    values = data.model_dump(exclude_unset=True)
    if values.get("is_active") is False and busy_wash(db, x.id):
        raise HTTPException(409, "This bay has a car on it. Finish that wash before closing the bay.")
    if "bay_number" in values and values["bay_number"] != x.bay_number and db.scalar(
            select(CarWashBay).where(CarWashBay.bay_number == values["bay_number"])):
        raise HTTPException(409, "Bay number already exists")
    before = bay_out(x)
    for key, value in values.items(): setattr(x, key, value)
    record(db, user, "update", "carwash_bays", x.id, before=before, after=bay_out(x))
    db.commit()
    return bay_out(x)


@router.put("/services/{service_id}")
def update_service(service_id: int, data: WashServiceUpdate, db: Session = Depends(get_db), user: User = Depends(config_auth)):
    """Changing a price affects new washes only; recorded washes keep their amount."""
    x = db.get(CarWashService, service_id)
    if not x: raise HTTPException(404, "Service not found")
    values = data.model_dump(exclude_unset=True)
    if "name" in values and values["name"] != x.name and db.scalar(select(CarWashService).where(CarWashService.name == values["name"])):
        raise HTTPException(409, "Service already exists")
    before = service_out(x)
    for key, value in values.items(): setattr(x, key, value)
    record(db, user, "update", "carwash_services", x.id, before=before, after=service_out(x))
    db.commit()
    return service_out(x)


@router.get("/attendants")
def attendants(db: Session = Depends(get_db), _=Depends(auth)):
    return [attendant_out(x) for x in db.scalars(select(CarWashAttendant).order_by(CarWashAttendant.name)).all()]


@router.post("/attendants", status_code=201)
def create_attendant(data: AttendantCreate, db: Session = Depends(get_db), user: User = Depends(config_auth)):
    x = CarWashAttendant(name=data.name, phone=data.phone)
    db.add(x); db.flush()
    record(db, user, "create", "carwash_attendants", x.id, after=attendant_out(x))
    db.commit()
    return attendant_out(x)


@router.put("/attendants/{attendant_id}")
def update_attendant(attendant_id: int, data: AttendantUpdate, db: Session = Depends(get_db), user: User = Depends(config_auth)):
    x = db.get(CarWashAttendant, attendant_id)
    if not x: raise HTTPException(404, "Attendant not found")
    before = attendant_out(x)
    for key, value in data.model_dump(exclude_unset=True).items(): setattr(x, key, value)
    record(db, user, "update", "carwash_attendants", x.id, before=before, after=attendant_out(x))
    db.commit()
    return attendant_out(x)
