from datetime import datetime
from decimal import Decimal
from sqlalchemy import UniqueConstraint, Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base
from .branch import BranchScoped
from .user import now

class Ingredient(BranchScoped, Base):
    __tablename__ = "ingredients"
    __table_args__ = (UniqueConstraint("branch_id", "name", name="uq_ingredient_branch_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    unit: Mapped[str] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(Text)
    reorder_quantity: Mapped[float] = mapped_column(Float, default=0)
    cost_per_unit: Mapped[float] = mapped_column(Float, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    min_level: Mapped[float] = mapped_column(Float)
    current_stock: Mapped[float] = mapped_column(Float, default=0)
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=now)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class StockTransaction(BranchScoped, Base):
    __tablename__ = "stock_transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"), index=True)
    transaction_type: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[float] = mapped_column(Float)
    quantity_before: Mapped[float | None] = mapped_column(Float)
    quantity_after: Mapped[float | None] = mapped_column(Float)
    reference_id: Mapped[int | None] = mapped_column(Integer)
    reference_type: Mapped[str | None] = mapped_column(String(40))
    reason: Mapped[str | None] = mapped_column(Text)
    # Ingredient cost per unit when the stock moved (empty for movements before Nov 2026).
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    performed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    ingredient: Mapped[Ingredient] = relationship()
