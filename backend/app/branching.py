"""Branch scoping for every request.

After sign-in, `apply_scope` records the branch a request works in on its database
session (`session.info`). Two session events then do the rest:

- Reads: every ORM query on a branch-owned model (BranchScoped) only returns rows from
  that branch. Directors working across all branches are not filtered.
- Writes: new branch-owned rows get their branch from the record they belong to (an
  order, a cashier shift or an ingredient) or, failing that, from the request's branch.

Sessions without a scope (startup, scripts, tests that use SessionLocal directly) are
not filtered.
"""
from fastapi import HTTPException
from sqlalchemy import event, select
from sqlalchemy.orm import Session, with_loader_criteria

from .models.branch import Branch, BranchScoped

SCOPE_KEY = "branch_scope"  # int branch id, or ALL
ALL = "all"

# Parent records whose branch a new row should inherit, checked in this order.
_PARENTS = (("order_id", "Order"), ("shift_id", "CashShift"), ("ingredient_id", "Ingredient"),
            ("payment_id", "Payment"), ("menu_item_id", None))


def active_branches(db: Session):
    return db.scalars(select(Branch).where(Branch.is_active.is_(True)).order_by(Branch.id)).all()


def apply_scope(db: Session, user, requested: str | None):
    """Set the request's branch. Returns the branch id, or None for all branches."""
    if user.role == "director" and user.branch_id is None:
        if requested in (None, "", ALL):
            db.info[SCOPE_KEY] = ALL
            return None
        try:
            identity = int(requested)
        except ValueError:
            raise HTTPException(400, "Unknown branch") from None
        branch = db.get(Branch, identity)
        if not branch:
            raise HTTPException(400, "Unknown branch")
        db.info[SCOPE_KEY] = branch.id
        return branch.id
    if user.branch_id is None:
        raise HTTPException(403, "This account is not assigned to a branch. Ask a director to assign one.")
    branch = db.get(Branch, user.branch_id)
    if not branch or not branch.is_active:
        raise HTTPException(403, "This branch is closed. Ask a director to reopen it or move your account.")
    db.info[SCOPE_KEY] = user.branch_id
    return user.branch_id


def scope(db: Session):
    """The request's branch id, ALL, or None when the session is unscoped."""
    return db.info.get(SCOPE_KEY)


def require_branch(db: Session) -> int:
    """Branch id that a new record should belong to.

    A director viewing all branches must pick one, unless only one branch exists.
    """
    current = scope(db)
    if isinstance(current, int):
        return current
    branches = active_branches(db)
    if len(branches) == 1:
        return branches[0].id
    raise HTTPException(400, "Select a branch before creating records.")


@event.listens_for(Session, "do_orm_execute")
def _filter_reads(state):
    current = state.session.info.get(SCOPE_KEY)
    if not isinstance(current, int) or not (state.is_select or state.is_update or state.is_delete):
        return
    if state.execution_options.get("all_branches"):
        return
    state.statement = state.statement.options(
        with_loader_criteria(BranchScoped, lambda cls: cls.branch_id == current, include_aliases=True))


@event.listens_for(Session, "before_flush")
def _stamp_new_rows(session, _context, _instances):
    from . import models
    current = session.info.get(SCOPE_KEY)
    for obj in session.new:
        if not isinstance(obj, BranchScoped) or obj.branch_id is not None:
            continue
        for attribute, model in _PARENTS:
            identity = getattr(obj, attribute, None)
            if identity is None or model is None:
                continue
            parent = session.get(getattr(models, model), identity)
            if parent is not None and parent.branch_id is not None:
                obj.branch_id = parent.branch_id
                break
        if obj.branch_id is None and current is not None:
            obj.branch_id = require_branch(session)
        if obj.branch_id is None and current is None:
            # Unscoped sessions (startup, scripts): only one branch can be meant.
            branches = active_branches(session)
            if len(branches) == 1:
                obj.branch_id = branches[0].id
        if obj.branch_id is None:
            raise HTTPException(400, "Select a branch before creating records.")


def switched_off(db: Session, branch_id) -> set[int]:
    """Menu item ids switched off at a branch (empty for all-branch views)."""
    from .models.branch import BranchMenuItem
    if not isinstance(branch_id, int):
        return set()
    return set(db.scalars(select(BranchMenuItem.menu_item_id).where(
        BranchMenuItem.branch_id == branch_id, BranchMenuItem.available.is_(False))).all())
