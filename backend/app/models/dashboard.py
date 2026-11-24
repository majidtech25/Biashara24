"""Live reports remain authoritative; snapshots and audit history are persisted."""
from decimal import Decimal
from datetime import date, datetime
from sqlalchemy import UniqueConstraint, Date, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Money, Base
from .branch import BranchScoped
from .user import now

class DailySummary(BranchScoped, Base):
    __tablename__ = "daily_summaries"
    __table_args__ = (UniqueConstraint("branch_id", "summary_date", name="uq_daily_summary_branch_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    summary_date: Mapped[date] = mapped_column(Date)
    restaurant_orders_count: Mapped[int] = mapped_column(Integer, default=0)
    restaurant_revenue: Mapped[Decimal] = mapped_column(Money, default=0)
    restaurant_cash: Mapped[Decimal] = mapped_column(Money, default=0)
    restaurant_mpesa: Mapped[Decimal] = mapped_column(Money, default=0)
    carwash_count: Mapped[int] = mapped_column(Integer, default=0)
    carwash_revenue: Mapped[Decimal] = mapped_column(Money, default=0)
    carwash_cash: Mapped[Decimal] = mapped_column(Money, default=0)
    carwash_mpesa: Mapped[Decimal] = mapped_column(Money, default=0)
    low_stock_items: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(80))
    module: Mapped[str] = mapped_column(String(50))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int] = mapped_column(Integer)
    old_values: Mapped[dict | None] = mapped_column(JSON)
    new_values: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(80))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
