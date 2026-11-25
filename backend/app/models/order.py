from decimal import Decimal
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Money, Base
from .branch import BranchScoped
from .user import User, now

class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Department(Base):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    printer_ip: Mapped[str | None] = mapped_column(String(80))
    printer_port: Mapped[int] = mapped_column(Integer, default=9100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class MenuItem(Base):
    __tablename__ = "menu_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    price: Mapped[Decimal] = mapped_column(Money)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), index=True)
    image_url: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(String(500))
    tax_rate: Mapped[int] = mapped_column(Integer, default=16)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    category: Mapped[Category] = relationship()
    department: Mapped[Department] = relationship()

class Order(BranchScoped, Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int | None] = mapped_column(ForeignKey("dining_tables.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    order_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    waiter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    customer: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
    total: Mapped[Decimal] = mapped_column(Money, default=0)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime)
    order_type: Mapped[str] = mapped_column(String(20), default="dine_in", server_default="dine_in")  # or "takeaway"
    split_from_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))  # bill this one was split from
    waiter: Mapped[User] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan", lazy="selectin",
                                                 order_by="OrderItem.id")  # submission order on every database

class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    voided_quantity: Mapped[int] = mapped_column(Integer, default=0)
    price_at_time: Mapped[Decimal] = mapped_column(Money)
    tax_rate_at_time: Mapped[int | None] = mapped_column(Integer)
    name_at_time: Mapped[str | None] = mapped_column(String(120))
    department_id_at_time: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    department_name_at_time: Mapped[str | None] = mapped_column(String(80))
    ready: Mapped[bool] = mapped_column(Boolean, default=False)
    order: Mapped[Order] = relationship(back_populates="items")
    menu_item: Mapped[MenuItem] = relationship(lazy="joined")

class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30))
    changed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class MenuImage(Base):
    __tablename__ = "menu_images"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    content_type: Mapped[str] = mapped_column(String(30))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=now)
