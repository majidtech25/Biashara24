"""Table ownership, immutable kitchen submissions and reviewed bill changes."""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base
from .branch import BranchScoped
from .user import now

class DiningTable(BranchScoped, Base):
    __tablename__ = "dining_tables"
    __table_args__ = (UniqueConstraint("branch_id", "number", name="uq_dining_table_branch_number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class TableReservation(Base):
    __tablename__ = "table_reservations"
    table_id: Mapped[int] = mapped_column(ForeignKey("dining_tables.id"), primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)

class OrderBatch(Base):
    __tablename__ = "order_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    items: Mapped[list] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)
    deliveries: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class BillSubmission(Base):
    __tablename__ = "bill_submissions"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_bill_submission_user_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    key: Mapped[str] = mapped_column(String(100))
    fingerprint: Mapped[str] = mapped_column(String(64))
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    batch_id: Mapped[int] = mapped_column(ForeignKey("order_batches.id"))

class BillChangeRequest(BranchScoped, Base):
    __tablename__ = "bill_change_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    items: Mapped[list] = mapped_column(JSON, default=list)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
