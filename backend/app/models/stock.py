from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import UniqueConstraint, Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text
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
    packs: Mapped[list["IngredientPack"]] = relationship(lazy="selectin", order_by="IngredientPack.name",
                                                         cascade="all, delete-orphan")

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


class IngredientPack(Base):
    """A pack an ingredient is bought or counted in, e.g. a 50 kg bag or a crate of 24 bottles."""
    __tablename__ = "ingredient_packs"
    __table_args__ = (UniqueConstraint("ingredient_id", "name", name="uq_ingredient_pack_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(40))
    factor: Mapped[Decimal] = mapped_column(Numeric(14, 6))  # stock units in one pack
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class StockBatch(BranchScoped, Base):
    """Stock received with an expiry date. Stock taken out uses the batch that expires first."""
    __tablename__ = "stock_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"), index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("stock_documents.id"))
    quantity: Mapped[float] = mapped_column(Float)
    remaining: Mapped[float] = mapped_column(Float)
    expiry_date: Mapped[date] = mapped_column(Date, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=now)
