"""Initial company accounts, created only when their email is not present."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..middleware.auth import hash_password, verify_password
from ..models import User

INITIAL_ACCOUNTS = (
    ("director", "director@gmail.com", "director123", "Director"),
    ("manager", "manager@gmail.com", "manager123", "Manager"),
    ("cashier", "cashier@gmail.com", "cashier123", "Cashier"),
    ("waiter", "waiter@gmail.com", "waiter123", "Waiter"),
    ("store_manager", "store@gmail.com", "store123", "Store Manager"),
    ("carwash_manager", "carwash@gmail.com", "carwash123", "Car Wash Manager"),
)


def seed_company_accounts(db: Session) -> None:
    for role, email, password, name in INITIAL_ACCOUNTS:
        if not db.scalar(select(User).where(User.username == email)):
            db.add(User(username=email, password_hash=hash_password(password), role=role, full_name=name))
    # The caller commits. Existing accounts and changed passwords are preserved.


def disable_default_accounts(db: Session) -> list[str]:
    """Production safety: deactivate initial accounts that still use their published password.

    Returns the affected emails. Accounts whose password was changed are left alone.
    The caller commits.
    """
    disabled = []
    for _role, email, password, _name in INITIAL_ACCOUNTS:
        user = db.scalar(select(User).where(User.username == email))
        if user and user.active and verify_password(password, user.password_hash):
            user.active = False
            user.token_version += 1  # end any open sessions
            disabled.append(email)
    return disabled
