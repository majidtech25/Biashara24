from decimal import Decimal
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from ..database import get_db
from ..middleware.auth import require_roles
from ..models import Ingredient, StockTransaction, User
from ..schemas import IngredientCreate, IngredientUpdate, StockChange
from ..utils.helpers import money, date_window
from ..services.audit import record
from ..services.bill_lock import start_write
from ..services.transactions import begin_submission, finish_submission

router = APIRouter(prefix="/api/stock", tags=["Stock"])
auth = require_roles("store_manager", "manager", "director")

def ingredient_dict(x):
    return {k: getattr(x, k) for k in ("id", "name", "unit", "description", "min_level", "current_stock",
            "reorder_quantity", "cost_per_unit", "is_active", "last_updated")} | {"is_low": x.current_stock < x.min_level}

def transaction_dict(x):
    return {"id": x.id, "ingredient_id": x.ingredient_id, "ingredient": x.ingredient.name,
            "type": x.transaction_type, "quantity": x.quantity, "quantity_before": x.quantity_before,
            "quantity_after": x.quantity_after, "reason": x.reason, "performed_by": x.performed_by, "timestamp": x.timestamp}

@router.get("")
@router.get("/ingredients")
def list_stock(low_only: bool = False, db: Session = Depends(get_db), _=Depends(auth)):
    q = select(Ingredient).order_by(Ingredient.name)
    if low_only: q = q.where(Ingredient.current_stock < Ingredient.min_level)
    return [ingredient_dict(x) for x in db.scalars(q).all()]

@router.post("/ingredients", status_code=201)
def create_ingredient(data: IngredientCreate, db: Session = Depends(get_db), user: User = Depends(auth)):
    if not data.name.strip() or not data.unit.strip(): raise HTTPException(400, "Name and unit are required")
    if db.scalar(select(Ingredient).where(func.lower(Ingredient.name) == data.name.lower())):
        raise HTTPException(409, "Ingredient already exists")
    x = Ingredient(**data.model_dump()); db.add(x); db.flush()
    if x.current_stock:
        db.add(StockTransaction(ingredient_id=x.id, transaction_type="add", quantity=x.current_stock,
               quantity_before=0, quantity_after=x.current_stock, reason="Opening stock", performed_by=user.id,
               unit_cost=Decimal(str(x.cost_per_unit or 0))))
    record(db, user, "create", "ingredients", x.id, after={"name": x.name, "current_stock": x.current_stock})
    db.commit(); db.refresh(x)
    return ingredient_dict(x)

@router.put("/ingredients/{ingredient_id}")
def update_ingredient(ingredient_id: int, data: IngredientUpdate, db: Session = Depends(get_db), user: User = Depends(auth)):
    """Change an ingredient's details. A new cost applies to stock moved from now on;
    food already prepared keeps the cost recorded when it was taken out of stock."""
    x = db.scalar(select(Ingredient).where(Ingredient.id == ingredient_id).with_for_update())
    if not x: raise HTTPException(404, "Ingredient not found")
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes:
        changes["name"] = changes["name"].strip()
        if db.scalar(select(Ingredient.id).where(func.lower(Ingredient.name) == changes["name"].lower(), Ingredient.id != x.id)):
            raise HTTPException(409, "Ingredient already exists")
    before = {k: getattr(x, k) for k in changes}
    for key, value in changes.items(): setattr(x, key, value)
    record(db, user, "update", "ingredients", x.id, before=before, after=changes)
    db.commit(); db.refresh(x)
    return ingredient_dict(x)

@router.get("/ingredients/{ingredient_id}")
def get_ingredient(ingredient_id: int, db: Session = Depends(get_db), _=Depends(auth)):
    x = db.get(Ingredient, ingredient_id)
    if not x: raise HTTPException(404, "Ingredient not found")
    tx = db.scalars(select(StockTransaction).where(StockTransaction.ingredient_id == x.id).order_by(StockTransaction.id.desc()).limit(20)).all()
    return ingredient_dict(x) | {"transactions": [transaction_dict(t) for t in tx]}

@router.get("/low-items")
def low_items(db: Session = Depends(get_db), _=Depends(auth)):
    rows = db.scalars(select(Ingredient).where(Ingredient.current_stock < Ingredient.min_level)).all()
    return {"count": len(rows), "items": [ingredient_dict(x) for x in rows]}

@router.get("/history")
def history(ingredient_id: int | None = None, transaction_type: str | None = None,
            from_date: date | None = None, to_date: date | None = None,
            limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
            db: Session = Depends(get_db), _=Depends(auth)):
    q = select(StockTransaction).order_by(StockTransaction.id.desc())
    if ingredient_id: q = q.where(StockTransaction.ingredient_id == ingredient_id)
    if transaction_type: q = q.where(StockTransaction.transaction_type == transaction_type)
    if from_date: q = q.where(StockTransaction.timestamp >= date_window(from_date)[0])
    if to_date: q = q.where(StockTransaction.timestamp < date_window(to_date)[1])
    return [transaction_dict(x) for x in db.scalars(q.offset(offset).limit(limit)).all()]

def change_stock(data, kind, db, user, key=None):
    start_write(db)
    submission, replay = begin_submission(db, user, key, 'stock:' + kind, data.model_dump())
    if replay is not None: return replay
    x = db.scalar(select(Ingredient).where(Ingredient.id == data.ingredient_id).with_for_update())
    if not x: raise HTTPException(404, "Ingredient not found")
    before = x.current_stock
    after = before + data.quantity if kind == "add" else before - data.quantity if kind == "deduction" else data.quantity
    if after < 0: raise HTTPException(409, "Insufficient stock")
    from ..services.production import reserved
    if after < reserved(db, x.id): raise HTTPException(409, 'This stock is reserved for submitted food. Resolve those orders first.')
    result = db.execute(update(Ingredient).where(Ingredient.id == x.id, Ingredient.current_stock == before)
                        .values(current_stock=after, last_updated=func.now()).execution_options(synchronize_session=False))
    if result.rowcount != 1: db.rollback(); raise HTTPException(409, "Stock changed; reload and try again")
    t = StockTransaction(ingredient_id=x.id, transaction_type=kind, quantity=data.quantity,
                         quantity_before=before, quantity_after=after, reason=data.reason, performed_by=user.id,
                         unit_cost=Decimal(str(x.cost_per_unit or 0)))
    db.add(t); db.flush()
    record(db, user, kind, "stock", x.id, before={"quantity": before}, after={"quantity": after})
    db.refresh(x)
    response = ingredient_dict(x) | {"transaction_id": t.id, "new_stock_level": after, "old_quantity": before, "new_quantity": after}
    finish_submission(submission, response)
    db.commit()
    return response

@router.post("/add", status_code=201)
def add(data: StockChange, db: Session = Depends(get_db), user: User = Depends(auth), idempotency_key: str | None = Header(None, min_length=8, max_length=100)): return change_stock(data, "add", db, user, idempotency_key)
@router.post("/adjust")
def adjust(data: StockChange, db: Session = Depends(get_db), user: User = Depends(auth), idempotency_key: str | None = Header(None, min_length=8, max_length=100)): return change_stock(data, "adjust", db, user, idempotency_key)
@router.post("/deduct")
def deduct(data: StockChange, db: Session = Depends(get_db), user: User = Depends(auth), idempotency_key: str | None = Header(None, min_length=8, max_length=100)): return change_stock(data, "deduction", db, user, idempotency_key)

@router.get("/usage-trends")
def trends(db: Session = Depends(get_db), _=Depends(auth)):
    rows = db.execute(select(Ingredient.name, Ingredient.unit, func.sum(StockTransaction.quantity)).join(StockTransaction)
           .where(StockTransaction.transaction_type == "deduction").group_by(Ingredient.id).order_by(func.sum(StockTransaction.quantity).desc())).all()
    return [{"ingredient": r[0], "unit": r[1], "total_used": money(r[2])} for r in rows]
