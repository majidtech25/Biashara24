from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, func
from ..models import Ingredient, StockTransaction, Recipe, StockReservation, KitchenLine, FoodWaste, StockBatch
from .audit import record


def quantity(value):
    return float(Decimal(str(value)).quantize(Decimal('0.000001')))


def reserved(db, ingredient_id):
    return float(db.scalar(select(func.coalesce(func.sum(StockReservation.quantity), 0)).where(StockReservation.ingredient_id == ingredient_id)))


def move(db, user, ingredient, delta, reason, reference_type, reference_id):
    before = ingredient.current_stock
    after = quantity(before + delta)
    if after < 0 or after + 0.000001 < reserved(db, ingredient.id):
        raise HTTPException(409, f'Insufficient unreserved stock for {ingredient.name}.')
    ingredient.current_stock = after
    if delta < 0:
        use_batches(db, ingredient.id, -delta)
    db.add(StockTransaction(ingredient_id=ingredient.id, transaction_type='add' if delta >= 0 else 'deduction',
           quantity=abs(delta), quantity_before=before, quantity_after=after, reason=reason,
           reference_type=reference_type, reference_id=reference_id, performed_by=user.id,
           unit_cost=Decimal(str(ingredient.cost_per_unit or 0))))
    record(db, user, reference_type, 'stock', ingredient.id, before={'quantity': before}, after={'quantity': after, 'reference_id': reference_id})


def use_batches(db, ingredient_id, amount):
    """Stock taken out comes from the batch that expires first."""
    left = quantity(amount)
    for batch in db.scalars(select(StockBatch).where(StockBatch.ingredient_id == ingredient_id, StockBatch.remaining > 0)
                            .order_by(StockBatch.expiry_date, StockBatch.id).with_for_update()).all():
        if left <= 0:
            break
        taken = min(batch.remaining, left)
        batch.remaining = quantity(batch.remaining - taken)
        left = quantity(left - taken)


def reserve_line(db, line):
    recipe = db.scalar(select(Recipe).where(Recipe.menu_item_id == line.menu_item_id).order_by(Recipe.version.desc()).limit(1))
    components = recipe.components if recipe else []
    state = KitchenLine(order_item_id=line.id, recipe_snapshot=components)
    db.add(state)
    for component in sorted(components, key=lambda x: x['ingredient_id']):
        ingredient = db.scalar(select(Ingredient).where(Ingredient.id == component['ingredient_id']).with_for_update())
        needed = quantity(component['quantity'] * line.quantity)
        if not ingredient or not ingredient.is_active or ingredient.current_stock - reserved(db, ingredient.id) + 0.000001 < needed:
            raise HTTPException(409, 'Insufficient ingredients for this order. Refresh availability.')
        db.add(StockReservation(order_item_id=line.id, ingredient_id=ingredient.id, quantity=needed))
    db.flush()


def start_preparation(db, line, state, user):
    reservations = db.scalars(select(StockReservation).where(StockReservation.order_item_id == line.id).order_by(StockReservation.ingredient_id).with_for_update()).all()
    for reservation in reservations:
        ingredient = db.scalar(select(Ingredient).where(Ingredient.id == reservation.ingredient_id).with_for_update())
        used = reservation.quantity
        db.delete(reservation)
        db.flush()
        move(db, user, ingredient, -used, 'Preparation started', 'preparation', line.id)
    db.flush()


def cancel_quantity(db, line, removed, reason, user):
    state = db.get(KitchenLine, line.id)
    if not state: return  # Legacy production history is unknown.
    if state.status == 'pending':
        remaining = line.quantity - line.voided_quantity - removed
        for reservation in db.scalars(select(StockReservation).where(StockReservation.order_item_id == line.id)).all():
            component = next(c for c in state.recipe_snapshot if c['ingredient_id'] == reservation.ingredient_id)
            if remaining == 0: db.delete(reservation)
            else: reservation.quantity = quantity(component['quantity'] * remaining)
    else:
        db.add(FoodWaste(order_item_id=line.id, quantity=removed, reason=reason, recorded_by=user.id,
                        ingredients=[{**c, 'quantity': quantity(c['quantity'] * removed)} for c in state.recipe_snapshot]))
    if line.quantity - line.voided_quantity == removed:
        state.status = 'cancelled'
    state.version += 1
