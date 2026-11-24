"""Restaurant production, inventory documents and cashier accountability."""
from decimal import Decimal
from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Money, Base
from .user import now


class Recipe(Base):
    __tablename__ = 'recipes'
    __table_args__ = (UniqueConstraint('menu_item_id', 'version'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey('menu_items.id'))
    version: Mapped[int] = mapped_column()
    components: Mapped[list] = mapped_column(JSON)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class StockReservation(Base):
    __tablename__ = 'stock_reservations'
    order_item_id: Mapped[int] = mapped_column(ForeignKey('order_items.id'), primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey('ingredients.id'), primary_key=True)
    quantity: Mapped[float] = mapped_column(Float)


class KitchenLine(Base):
    __tablename__ = 'kitchen_lines'
    order_item_id: Mapped[int] = mapped_column(ForeignKey('order_items.id'), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    version: Mapped[int] = mapped_column(default=1)
    recipe_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime)
    served_at: Mapped[datetime | None] = mapped_column(DateTime)


class FoodWaste(Base):
    __tablename__ = 'food_waste'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_item_id: Mapped[int] = mapped_column(ForeignKey('order_items.id'))
    quantity: Mapped[int] = mapped_column()
    reason: Mapped[str] = mapped_column(String(500))
    ingredients: Mapped[list] = mapped_column(JSON)
    recorded_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Notification(Base):
    __tablename__ = 'notifications'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    message: Mapped[str] = mapped_column(String(500))
    order_id: Mapped[int | None] = mapped_column(ForeignKey('orders.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)


class Supplier(Base):
    __tablename__ = 'suppliers'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    contact: Mapped[str] = mapped_column(String(200), default='')
    active: Mapped[bool] = mapped_column(default=True)


class StockDocument(Base):
    __tablename__ = 'stock_documents'
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey('suppliers.id'))
    reference: Mapped[str] = mapped_column(String(100))
    lines: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default='draft')
    reason: Mapped[str] = mapped_column(String(500))
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    posted_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime)


class CashShift(Base):
    __tablename__ = 'cash_shifts'
    id: Mapped[int] = mapped_column(primary_key=True)
    cashier_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    active_cashier_id: Mapped[int | None] = mapped_column(unique=True)
    opening_float: Mapped[Decimal] = mapped_column(Money)
    counted_cash: Mapped[Decimal | None] = mapped_column(Money)
    expected_cash: Mapped[Decimal | None] = mapped_column(Money)
    variance_reason: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default='open')
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)


class TillMovement(Base):
    __tablename__ = 'till_movements'
    id: Mapped[int] = mapped_column(primary_key=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey('cash_shifts.id'))
    amount: Mapped[Decimal] = mapped_column(Money)
    reason: Mapped[str] = mapped_column(String(500))
    recorded_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Refund(Base):
    __tablename__ = 'refunds'
    __table_args__ = (Index('ux_refund_reference', 'reference', unique=True),)
    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey('payments.id'))
    shift_id: Mapped[int | None] = mapped_column(ForeignKey('cash_shifts.id'))
    amount: Mapped[Decimal] = mapped_column(Money)
    reason: Mapped[str] = mapped_column(String(500))
    reference: Mapped[str | None] = mapped_column(String(100))
    recorded_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class BusinessSettings(Base):
    __tablename__ = 'business_settings'
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(default=1)
    values: Mapped[dict] = mapped_column(JSON)
