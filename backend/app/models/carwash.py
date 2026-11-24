from decimal import Decimal
from datetime import datetime
from sqlalchemy import UniqueConstraint, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Money, Base
from .branch import BranchScoped
from .user import now

class CarWashBay(BranchScoped, Base):
    __tablename__ = "carwash_bays"
    __table_args__ = (UniqueConstraint("branch_id", "bay_number", name="uq_carwash_bay_branch_number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    bay_number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class CarWashService(Base):
    __tablename__ = "carwash_services"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Money)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class CarWashTransaction(BranchScoped, Base):
    __tablename__ = "carwash_transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_number: Mapped[str | None] = mapped_column(String(40), unique=True)
    bay_id: Mapped[int | None] = mapped_column(ForeignKey("carwash_bays.id"), index=True)
    service_id: Mapped[int | None] = mapped_column(ForeignKey("carwash_services.id"))
    vehicle_type: Mapped[str | None] = mapped_column(String(50))
    mpesa_reference: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    vehicle_plate: Mapped[str] = mapped_column(String(20), index=True)
    payment_method: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Money)
    payment_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    notes: Mapped[str | None] = mapped_column(Text)
    shift_id: Mapped[int | None] = mapped_column(ForeignKey('cash_shifts.id'))
    service_name_at_time: Mapped[str | None] = mapped_column(String(100))
    # The wash itself, separate from payment: waiting -> washing -> done.
    wash_status: Mapped[str] = mapped_column(String(20), default="waiting", index=True)
    attendant_id: Mapped[int | None] = mapped_column(ForeignKey("carwash_attendants.id"), index=True)
    wash_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    wash_finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class CarWashAttendant(BranchScoped, Base):
    """A person who washes cars at a branch. Attendants do not sign in."""
    __tablename__ = "carwash_attendants"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(30))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
