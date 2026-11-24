"""M-Pesa Express prompts (STK push) sent to a customer's phone."""
from decimal import Decimal
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, JSON
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Money, Base
from .branch import BranchScoped
from .user import now


class MpesaRequest(BranchScoped, Base):
    """One prompt. Status: waiting -> paid | failed | unmatched (paid, but the bill or wash
    could no longer take it) -> resolved (a manager dealt with an unmatched payment)."""
    __tablename__ = "mpesa_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    checkout_request_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    merchant_request_id: Mapped[str | None] = mapped_column(String(100))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    carwash_id: Mapped[int | None] = mapped_column(ForeignKey("carwash_transactions.id"), index=True)
    phone: Mapped[str] = mapped_column(String(15))
    amount: Mapped[Decimal] = mapped_column(Money)
    status: Mapped[str] = mapped_column(String(20), default="waiting", index=True)
    result_code: Mapped[str | None] = mapped_column(String(20))
    result_desc: Mapped[str | None] = mapped_column(String(300))
    receipt: Mapped[str | None] = mapped_column(String(30), unique=True)
    paid_amount: Mapped[Decimal | None] = mapped_column(Money)
    paid_phone: Mapped[str | None] = mapped_column(String(15))
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"))
    note: Mapped[str | None] = mapped_column(String(500))
    callback: Mapped[dict | None] = mapped_column(JSON)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
