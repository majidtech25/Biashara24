"""Branch administration and per-branch menu availability."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..branching import scope
from ..database import get_db
from ..middleware.auth import current_user, require_roles
from ..models import Branch, BranchMenuItem, MenuItem, User
from ..schemas import BaseModel
from ..services.audit import record

router = APIRouter(prefix="/api/branches", tags=["Branches"])
director = require_roles("director")
manager = require_roles("manager", "director")


class BranchCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=2, max_length=20, pattern=r"^[A-Za-z0-9-]+$")
    address: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=30)


class BranchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    address: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=30)
    is_active: bool | None = None


class Availability(BaseModel):
    available: bool


def _audit(b: Branch) -> dict:
    return {"id": b.id, "name": b.name, "code": b.code, "address": b.address, "phone": b.phone,
            "is_active": b.is_active}


def branch_dict(b: Branch) -> dict:
    return _audit(b) | {"created_at": b.created_at}


@router.get("")
def list_branches(db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = select(Branch).order_by(Branch.id)
    if isinstance(scope(db), int) and not (user.role == "director" and user.branch_id is None):
        query = query.where(Branch.id == scope(db))
    return [branch_dict(b) for b in db.scalars(query).all()]


@router.post("", status_code=201)
def create_branch(data: BranchCreate, db: Session = Depends(get_db), actor: User = Depends(director)):
    code = data.code.upper()
    if db.scalar(select(Branch).where((Branch.name == data.name) | (Branch.code == code))):
        raise HTTPException(409, "A branch with this name or code already exists")
    branch = Branch(name=data.name, code=code, address=data.address, phone=data.phone)
    db.add(branch)
    db.flush()
    record(db, actor, "create", "branches", branch.id, after=_audit(branch))
    db.commit()
    return branch_dict(branch)


@router.put("/{branch_id}")
def update_branch(branch_id: int, data: BranchUpdate, db: Session = Depends(get_db), actor: User = Depends(director)):
    branch = db.get(Branch, branch_id)
    if not branch:
        raise HTTPException(404, "Branch not found")
    before = _audit(branch)
    values = data.model_dump(exclude_unset=True)
    if values.get("is_active") is False and branch.is_active:
        others = db.scalars(select(Branch).where(Branch.is_active.is_(True), Branch.id != branch.id)).all()
        if not others:
            raise HTTPException(400, "At least one branch must stay active")
    if "name" in values and db.scalar(select(Branch).where(Branch.name == values["name"], Branch.id != branch.id)):
        raise HTTPException(409, "A branch with this name already exists")
    for key, value in values.items():
        setattr(branch, key, value)
    record(db, actor, "update", "branches", branch.id, before=before, after=_audit(branch))
    db.commit()
    return branch_dict(branch)


@router.get("/{branch_id}/menu")
def branch_menu(branch_id: int, db: Session = Depends(get_db), actor: User = Depends(manager)):
    _check_branch(db, actor, branch_id)
    off = {row.menu_item_id for row in db.scalars(select(BranchMenuItem).where(
        BranchMenuItem.branch_id == branch_id, BranchMenuItem.available.is_(False))).all()}
    items = db.scalars(select(MenuItem).where(MenuItem.active.is_(True)).order_by(MenuItem.name)).all()
    return [{"menu_item_id": m.id, "name": m.name, "available": m.id not in off} for m in items]


@router.put("/{branch_id}/menu/{menu_item_id}")
def set_availability(branch_id: int, menu_item_id: int, data: Availability, db: Session = Depends(get_db),
                     actor: User = Depends(manager)):
    _check_branch(db, actor, branch_id)
    if not db.get(MenuItem, menu_item_id):
        raise HTTPException(404, "Menu item not found")
    row = db.scalar(select(BranchMenuItem).where(BranchMenuItem.branch_id == branch_id,
                                                 BranchMenuItem.menu_item_id == menu_item_id))
    before = row.available if row else True
    if row is None:
        row = BranchMenuItem(branch_id=branch_id, menu_item_id=menu_item_id, available=data.available)
        db.add(row)
    else:
        row.available = data.available
    db.flush()
    record(db, actor, "set_availability", "branch_menu_items", row.id,
           before={"branch_id": branch_id, "menu_item_id": menu_item_id, "available": before},
           after={"branch_id": branch_id, "menu_item_id": menu_item_id, "available": data.available})
    db.commit()
    return {"branch_id": branch_id, "menu_item_id": menu_item_id, "available": data.available}


def _check_branch(db: Session, actor: User, branch_id: int):
    if not db.get(Branch, branch_id):
        raise HTTPException(404, "Branch not found")
    if actor.branch_id is not None and actor.branch_id != branch_id:
        raise HTTPException(403, "You can only manage your own branch")
