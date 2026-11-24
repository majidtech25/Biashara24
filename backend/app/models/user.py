from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base

def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey('departments.id'))
    # Home branch. Directors have none and can see every branch.
    branch_id: Mapped[int | None] = mapped_column(ForeignKey('branches.id'), index=True)
    full_name: Mapped[str | None] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    email: Mapped[str | None] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(30))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class RevokedToken(Base):
    __tablename__ = "revoked_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    jti: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
