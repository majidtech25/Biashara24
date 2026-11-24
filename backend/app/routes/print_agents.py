"""The print program at each branch.

The server is in the cloud and cannot reach printers on a restaurant's local network. While a
branch has an active print program, its kitchen tickets wait on the server; the program asks
for them every few seconds, prints them on the local network and reports the result.

Duplicate safety is the same as for direct printing: a ticket is marked "uncertain" when the
program collects it, before it prints. Only "sent" and "not_sent" (printer unreachable,
nothing printed) clear that mark; anything else needs a manager in Printer Recovery.
"""
import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..branching import scope
from ..database import get_db
from ..middleware.auth import require_roles
from ..models import Branch, Department, DiningTable, Order, PrintAgent
from ..models.waiter import OrderBatch
from ..schemas import BaseModel
from ..services.audit import record
from ..services.bill_lock import start_write
from ..services.printers_services import RETRY_LIMIT, RETRY_WINDOW_MINUTES, printer_for, render_ticket

router = APIRouter(prefix="/api/print-agents", tags=["Print programs"])
agent_api = APIRouter(prefix="/api/print-agent", tags=["Print programs"])
manager = require_roles("manager", "director")
JOB_WINDOW = timedelta(hours=12)  # tickets older than this are left for Printer Recovery
SEEN_RECENTLY = timedelta(minutes=2)


def digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def out(row: PrintAgent, db):
    branch = db.get(Branch, row.branch_id)
    online = bool(row.last_seen and datetime.utcnow() - row.last_seen < SEEN_RECENTLY)
    return {"id": row.id, "branch_id": row.branch_id, "branch": branch.name if branch else None, "name": row.name,
            "is_active": row.is_active, "last_seen": row.last_seen, "online": online and row.is_active}


def own_branch(db, branch_id):
    current = scope(db)
    if isinstance(current, int) and current != branch_id:
        raise HTTPException(403, "You can only manage the print program for your own branch.")


class AgentCreate(BaseModel):
    branch_id: int = Field(gt=0)
    name: str = Field(min_length=2, max_length=80)


@router.get("")
def agents(db: Session = Depends(get_db), _=Depends(manager)):
    rows = db.scalars(select(PrintAgent).order_by(PrintAgent.branch_id, PrintAgent.id)).all()
    current = scope(db)
    return [out(r, db) for r in rows if not isinstance(current, int) or r.branch_id == current]


@router.post("", status_code=201)
def add_agent(data: AgentCreate, db: Session = Depends(get_db), user=Depends(manager)):
    """Register a print program. The key is shown once; paste it into the program's settings."""
    start_write(db)
    if not db.get(Branch, data.branch_id): raise HTTPException(404, "Branch not found")
    own_branch(db, data.branch_id)
    key = "bpa_" + secrets.token_urlsafe(32)
    row = PrintAgent(branch_id=data.branch_id, name=data.name.strip(), token_hash=digest(key))
    db.add(row); db.flush()
    record(db, user, "create", "print_agents", row.id, after={"branch_id": row.branch_id, "name": row.name})
    db.commit()
    return out(row, db) | {"key": key}


@router.delete("/{identity}")
def revoke_agent(identity: int, db: Session = Depends(get_db), user=Depends(manager)):
    """Stop a print program. If it was the branch's last one, the server prints directly again."""
    start_write(db)
    row = db.get(PrintAgent, identity)
    if not row: raise HTTPException(404, "Print program not found")
    own_branch(db, row.branch_id)
    row.is_active = False
    record(db, user, "revoke", "print_agents", row.id, after={"is_active": False})
    db.commit()
    return out(row, db)


def agent_for(db, key: str | None) -> PrintAgent:
    if not key: raise HTTPException(401, "Print program key missing")
    row = db.scalar(select(PrintAgent).where(PrintAgent.token_hash == digest(key)))
    if not row or not row.is_active or not hmac.compare_digest(row.token_hash, digest(key)):
        raise HTTPException(401, "This print program key is not valid. Ask a manager for a new one.")
    return row


@agent_api.get("/jobs")
def collect(x_print_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Tickets waiting for this branch. Each one is marked as collected before it is returned."""
    start_write(db)
    agent = agent_for(db, x_print_agent_key)
    agent.last_seen = datetime.utcnow()
    since = datetime.utcnow() - JOB_WINDOW
    jobs = []
    batches = db.scalars(select(OrderBatch).join(Order, Order.id == OrderBatch.order_id)
                         .where(Order.branch_id == agent.branch_id, OrderBatch.created_at >= since)
                         .order_by(OrderBatch.id).with_for_update().execution_options(all_branches=True)).all()
    for batch in batches:
        if not any(d.get("status") == "queued" for d in batch.deliveries or []):
            continue
        order = db.get(Order, batch.order_id)
        table = db.get(DiningTable, order.table_id) if order.table_id else None
        deliveries = [dict(d) for d in batch.deliveries]
        for index, delivery in enumerate(deliveries):
            if delivery.get("status") != "queued" or len(jobs) >= 20:
                continue
            department = db.get(Department, delivery["department_id"])
            target = printer_for(db, department, order.branch_id)
            if not target:
                deliveries[index] = {**delivery, "status": "not_configured"}
                continue
            claim = secrets.token_hex(8)
            deliveries[index] = {**delivery, "status": "uncertain", "claim": claim, "agent_id": agent.id,
                                 "attempts": delivery.get("attempts", 0) + 1, "collected_at": datetime.utcnow().isoformat()}
            data = render_ticket(department, order, batch, [i for i in batch.items if i["department_id"] == department.id],
                                 table.number if table else None)
            jobs.append({"batch_id": batch.id, "department_id": department.id, "department": department.name, "claim": claim,
                         "printer_host": target[0], "printer_port": int(target[1]), "data": base64.b64encode(data).decode()})
        batch.deliveries = deliveries
    db.commit()  # the claims are saved before the program prints anything
    return {"jobs": jobs, "poll_seconds": 3}


class JobResult(BaseModel):
    batch_id: int
    department_id: int
    claim: str = Field(min_length=4, max_length=40)
    status: str = Field(pattern="^(sent|not_sent|uncertain)$")
    detail: str | None = Field(default=None, max_length=300)


@agent_api.post("/results")
def report(data: JobResult, x_print_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    start_write(db)
    agent = agent_for(db, x_print_agent_key)
    agent.last_seen = datetime.utcnow()
    batch = db.scalar(select(OrderBatch).where(OrderBatch.id == data.batch_id).with_for_update())
    order = db.get(Order, batch.order_id) if batch else None
    if not batch or not order or order.branch_id != agent.branch_id:
        raise HTTPException(404, "Ticket not found")
    deliveries = [dict(d) for d in batch.deliveries]
    index = next((i for i, d in enumerate(deliveries) if d["department_id"] == data.department_id), None)
    if index is None or deliveries[index].get("claim") != data.claim:
        db.commit()
        return {"accepted": False}  # a manager acted on this ticket meanwhile; keep their decision
    delivery = deliveries[index]
    status = data.status
    young = batch.created_at >= datetime.utcnow() - timedelta(minutes=RETRY_WINDOW_MINUTES)
    if status == "not_sent" and delivery.get("attempts", 1) < RETRY_LIMIT and young:
        status = "queued"  # nothing printed: the program will try again
    deliveries[index] = {**{k: v for k, v in delivery.items() if k != "claim"}, "status": status,
                         **({"detail": data.detail} if data.detail else {})}
    batch.deliveries = deliveries
    db.commit()
    return {"accepted": True, "status": status}


def agent_branch(db, branch_id) -> bool:
    """True while the branch's tickets go through a print program."""
    return branch_id is not None and db.scalar(
        select(PrintAgent.id).where(PrintAgent.branch_id == branch_id, PrintAgent.is_active.is_(True)).limit(1)) is not None
