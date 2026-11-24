"""M-Pesa Paybill payments reported by Safaricom (C2B confirmation)."""
from decimal import Decimal
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, JSON
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Money, Base
from .user import now


class C2BPayment(Base):
    """One payment into the business Paybill.

    status: received (not yet used by staff) -> used (a cashier confirmed it against a bill
    or car wash). Not branch-scoped through the mixin: Safaricom's notification arrives
    without a branch. branch_id is set from the bill or wash the account number matches.
    """
    __tablename__ = "c2b_payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    trans_id: Mapped[str] = mapped_column(String(30), unique=True)
    trans_type: Mapped[str | None] = mapped_column(String(30))
    trans_time: Mapped[str | None] = mapped_column(String(14))
    amount: Mapped[Decimal] = mapped_column(Money)
    account: Mapped[str | None] = mapped_column(String(40), index=True)
    msisdn: Mapped[str | None] = mapped_column(String(30))
    payer_name: Mapped[str | None] = mapped_column(String(120))
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    carwash_id: Mapped[int | None] = mapped_column(ForeignKey("carwash_transactions.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="received", index=True)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"))
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
    raw: Mapped[dict | None] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
