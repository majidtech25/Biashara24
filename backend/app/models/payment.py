from decimal import Decimal
from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Money, Base
from .branch import BranchScoped
from .user import now

class Payment(BranchScoped, Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    active_order_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    method: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default="completed", index=True)
    notes: Mapped[str | None] = mapped_column(String(500))
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reference: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime)
    rejected_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    rejection_reason: Mapped[str | None] = mapped_column(String(500))
    receipt_snapshot: Mapped[dict | None] = mapped_column(JSON)
    shift_id: Mapped[int | None] = mapped_column(ForeignKey('cash_shifts.id'))
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    tendered_amount: Mapped[Decimal | None] = mapped_column(Money)
    change_amount: Mapped[Decimal | None] = mapped_column(Money)
    order: Mapped["Order"] = relationship()

from .order import Order
