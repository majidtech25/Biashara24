"""Branches (business locations) and per-branch menu availability."""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, declared_attr, mapped_column
from ..database import Base
from .user import now


class Branch(Base):
    __tablename__ = "branches"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    address: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(30))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class BranchScoped:
    """Mixin for records that belong to one branch.

    Reads are filtered to the signed-in user's branch and new rows are stamped with it
    automatically (see app/branching.py). The column is nullable at database level only so
    older databases can be upgraded in place; the app never writes a row without it.
    """

    @declared_attr
    def branch_id(cls) -> Mapped[int | None]:
        return mapped_column(ForeignKey("branches.id"), index=True, nullable=True)


class BranchMenuItem(Base):
    """A menu item switched off at one branch. Absent row means available."""
    __tablename__ = "branch_menu_items"
    __table_args__ = (UniqueConstraint("branch_id", "menu_item_id", name="uq_branch_menu_item"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id"), index=True)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class BranchPrinter(Base):
    """A department's printer at one branch. Without one, the department's own printer is used."""
    __tablename__ = "branch_printers"
    __table_args__ = (UniqueConstraint("branch_id", "department_id", name="uq_branch_printer"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), index=True)
    printer_ip: Mapped[str] = mapped_column(String(80))
    printer_port: Mapped[int] = mapped_column(default=9100)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
