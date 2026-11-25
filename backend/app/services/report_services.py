from datetime import date, timedelta
from fastapi import HTTPException
from sqlalchemy import func, select
from ..models import Payment, CarWashTransaction, Ingredient, MenuItem, OrderItem, Refund
from ..utils.helpers import business_today, date_window, money

def validate_range(start, end):
    if start > end: raise HTTPException(400, "Start date must precede end date")
    if (end - start).days > 366: raise HTTPException(400, "Choose a range of at most 367 days")

def revenue(db, start, end):
    pay = dict(db.execute(select(Payment.method, func.sum(Payment.amount)).where(
        Payment.status == "completed", Payment.completed_at >= start, Payment.completed_at < end).group_by(Payment.method)).all())
    refunded = dict(db.execute(select(Payment.method, func.sum(Refund.amount)).join(Refund, Refund.payment_id == Payment.id).where(
        Refund.created_at >= start, Refund.created_at < end).group_by(Payment.method)).all())
    wash = dict(db.execute(select(CarWashTransaction.payment_method, func.sum(CarWashTransaction.amount)).where(
        CarWashTransaction.payment_status == "completed", CarWashTransaction.completed_at >= start,
        CarWashTransaction.completed_at < end).group_by(CarWashTransaction.payment_method)).all())
    def section(values):
        cash, mpesa = money(values.get("cash", 0)), money(values.get("m-pesa", 0))
        return {"cash": cash, "m_pesa": mpesa, "total": money(cash + mpesa)}
    restaurant = section(pay)
    refunds = money(sum(refunded.values()))
    return {**restaurant, 'gross_total': restaurant['total'], 'refunds': refunds,
            'cash': money(restaurant['cash'] - refunded.get('cash', 0)),
            'm_pesa': money(restaurant['m_pesa'] - refunded.get('m-pesa', 0)),
            'total': money(restaurant['total'] - refunds)}, section(wash)

def top_items(db, start, end, limit=5):
    historical_name = func.coalesce(OrderItem.name_at_time, MenuItem.name)
    rows = db.execute(select(historical_name, func.sum(OrderItem.quantity - OrderItem.voided_quantity), func.sum((OrderItem.quantity - OrderItem.voided_quantity) * OrderItem.price_at_time))
        .select_from(MenuItem).join(OrderItem, OrderItem.menu_item_id == MenuItem.id).join(Payment, Payment.order_id == OrderItem.order_id)
        .where(Payment.status == "completed", Payment.completed_at >= start, Payment.completed_at < end)
        .group_by(MenuItem.id, historical_name).order_by(func.sum(OrderItem.quantity - OrderItem.voided_quantity).desc(), historical_name).limit(limit)).all()
    return [{"item": r[0], "quantity": r[1], "revenue": money(r[2])} for r in rows]

def low_stock(db):
    return [{"id": x.id, "ingredient": x.name, "current": x.current_stock, "min": x.min_level, "unit": x.unit}
            for x in db.scalars(select(Ingredient).where(Ingredient.current_stock < Ingredient.min_level)).all()]

def daily_data(db, day):
    start, end = date_window(day)
    r, c = revenue(db, start, end)
    count = db.scalar(select(func.count()).select_from(Payment).where(Payment.status == "completed", Payment.completed_at >= start, Payment.completed_at < end))
    washes = db.scalar(select(func.count()).select_from(CarWashTransaction).where(CarWashTransaction.payment_status == "completed",
                       CarWashTransaction.completed_at >= start, CarWashTransaction.completed_at < end))
    return {"date": day, "restaurant": {**r, "revenue": r["total"], "orders_count": count, "top_items": top_items(db, start, end)},
            "carwash": {**c, "revenue": c["total"], "washes_count": washes},
            "stock": {"low_items": low_stock(db)}, "total": money(r["total"] + c["total"])}

def build(db, first, last):
    validate_range(first, last)
    days = []
    day = first
    while day <= last:
        data = daily_data(db, day)
        days.append({"date": day, "restaurant": data["restaurant"]["revenue"], "carwash": data["carwash"]["revenue"],
                     "restaurant_gross":data['restaurant']['gross_total'], "restaurant_refunds":data['restaurant']['refunds'],
                     "total": data["total"], "restaurant_cash": data["restaurant"]["cash"], "restaurant_mpesa": data["restaurant"]["m_pesa"],
                     "carwash_cash": data["carwash"]["cash"], "carwash_mpesa": data["carwash"]["m_pesa"],
                     "orders_count": data["restaurant"]["orders_count"], "washes_count": data["carwash"]["washes_count"]})
        day += timedelta(days=1)
    start, end = date_window(first)[0], date_window(last)[1]
    return {"start": first, "end": last, "days": days, "stock": {"low_items": low_stock(db), "as_of": business_today()},
            "top_items": top_items(db, start, end, 20),
            "totals": {"restaurant": money(sum(x["restaurant"] for x in days)), "carwash": money(sum(x["carwash"] for x in days)),
                       "restaurant_gross":money(sum(x['restaurant_gross'] for x in days)), "restaurant_refunds":money(sum(x['restaurant_refunds'] for x in days)),
                       "combined": money(sum(x["total"] for x in days))}}

def pdf_document(lines):
    """Small multi-page text PDF; byte offsets are calculated after encoding."""
    pages = [lines[i:i+46] for i in range(0, len(lines), 46)] or [[]]
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for page in pages:
        page_id = len(objects) + 1; stream_id = page_id + 1; kids.append(f"{page_id} 0 R")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {stream_id} 0 R >>".encode())
        commands = ["BT /F1 10 Tf 40 800 Td 16 TL"]
        for line in page:
            escaped = str(line).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.append(f"({escaped}) Tj T*")
        stream = ("\n".join(commands) + "\nET").encode("latin-1", errors="replace")
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode()
    result = b"%PDF-1.4\n"; offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(result)); result += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(result)
    result += f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode()
    result += b"".join(f"{n:010d} 00000 n \n".encode() for n in offsets[1:])
    return result + f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()


# ---- profit and VAT -------------------------------------------------------------------------
# Restaurant prices include VAT, so VAT is taken out of each line at the rate recorded when it was
# sold. Food cost is the ingredients taken out of stock when each sold line was prepared, at the
# ingredient cost recorded on that stock movement (or today's cost for movements made before
# costs were recorded, which the report counts as estimates).

def _d(value):
    from decimal import Decimal
    return Decimal(str(value or 0))


def profit_vat(db, first, last):
    from collections import defaultdict
    from decimal import Decimal, ROUND_HALF_UP
    from ..models import StockTransaction
    from ..utils.tax import vat_amount
    validate_range(first, last)
    start, end = date_window(first)[0], date_window(last)[1]
    cents = lambda v: float(Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    paid = db.execute(select(Payment.id, Payment.order_id, Payment.amount).where(
        Payment.status == "completed", Payment.completed_at >= start, Payment.completed_at < end)).all()
    order_ids = sorted({p.order_id for p in paid})
    lines = db.scalars(select(OrderItem).where(OrderItem.order_id.in_(order_ids))).all() if order_ids else []

    # Ingredient cost of each sold line, from its preparation stock movements.
    cost_by_line, estimated_lines = defaultdict(Decimal), set()
    line_ids = [l.id for l in lines]
    if line_ids:
        moves = db.execute(select(StockTransaction.reference_id, StockTransaction.quantity, StockTransaction.unit_cost,
                                  Ingredient.cost_per_unit).join(Ingredient, Ingredient.id == StockTransaction.ingredient_id)
                           .where(StockTransaction.reference_type == "preparation", StockTransaction.reference_id.in_(line_ids))).all()
        for line_id, qty, unit_cost, current_cost in moves:
            if unit_cost is None:
                estimated_lines.add(line_id)
            cost_by_line[line_id] += _d(qty) * _d(unit_cost if unit_cost is not None else current_cost)
        prepared = {m[0] for m in moves}
    else:
        prepared = set()

    by_rate = defaultdict(lambda: {"gross": Decimal(0), "vat": Decimal(0)})
    items = defaultdict(lambda: {"quantity": 0, "gross": Decimal(0), "vat": Decimal(0), "cost": Decimal(0), "no_cost": 0})
    order_vat, order_gross, unknown_rate = defaultdict(Decimal), defaultdict(Decimal), Decimal(0)
    for line in lines:
        qty = line.quantity - line.voided_quantity
        if qty <= 0:
            continue
        gross = _d(line.price_at_time) * qty
        rate = line.tax_rate_at_time
        vat = vat_amount(gross, rate) if rate is not None else Decimal(0)
        if rate is None:
            unknown_rate += gross
        else:
            by_rate[rate]["gross"] += gross; by_rate[rate]["vat"] += vat
        order_vat[line.order_id] += vat; order_gross[line.order_id] += gross
        name = line.name_at_time or (line.menu_item.name if line.menu_item else f"Item {line.menu_item_id}")
        row = items[name]
        row["quantity"] += qty; row["gross"] += gross; row["vat"] += vat; row["cost"] += cost_by_line.get(line.id, Decimal(0))
        if line.id not in prepared:
            row["no_cost"] += qty

    # Refunds (credit notes) in the period. Their VAT follows the VAT share of the refunded bill.
    refunds = db.execute(select(Refund.amount, Payment.order_id).join(Payment, Payment.id == Refund.payment_id)
                         .where(Refund.created_at >= start, Refund.created_at < end)).all()
    refund_gross, refund_vat = Decimal(0), Decimal(0)
    missing = {r.order_id for r in refunds} - set(order_gross)
    if missing:
        for line in db.scalars(select(OrderItem).where(OrderItem.order_id.in_(sorted(missing)))).all():
            qty = line.quantity - line.voided_quantity
            if qty > 0:
                gross = _d(line.price_at_time) * qty
                order_gross[line.order_id] += gross
                order_vat[line.order_id] += vat_amount(gross, line.tax_rate_at_time) if line.tax_rate_at_time is not None else 0
    for amount, order_id in refunds:
        refund_gross += _d(amount)
        if order_gross.get(order_id):
            refund_vat += (_d(amount) * order_vat[order_id] / order_gross[order_id]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    sales_gross = sum((v["gross"] for v in by_rate.values()), Decimal(0)) + unknown_rate
    sales_vat = sum((v["vat"] for v in by_rate.values()), Decimal(0))
    food_cost = sum((v["cost"] for v in items.values()), Decimal(0))
    net_sales = sales_gross - sales_vat - (refund_gross - refund_vat)

    # Stock written off or found short in counts during the period (not part of food cost above).
    write_offs = db.execute(select(StockTransaction.reference_type, StockTransaction.transaction_type, StockTransaction.quantity,
                                   StockTransaction.unit_cost, Ingredient.cost_per_unit)
                            .join(Ingredient, Ingredient.id == StockTransaction.ingredient_id)
                            .where(StockTransaction.reference_type.in_(("wastage", "count")),
                                   StockTransaction.timestamp >= start, StockTransaction.timestamp < end)).all()
    wastage = Decimal(0)
    for kind, direction, qty, unit_cost, current_cost in write_offs:
        value = _d(qty) * _d(unit_cost if unit_cost is not None else current_cost)
        wastage += value if direction == "deduction" else -value

    wash = _d(db.scalar(select(func.coalesce(func.sum(CarWashTransaction.amount), 0)).where(
        CarWashTransaction.payment_status == "completed", CarWashTransaction.completed_at >= start, CarWashTransaction.completed_at < end)))

    gross_profit = net_sales - food_cost
    return {
        "from_date": first, "to_date": last,
        "restaurant": {
            "sales_gross": cents(sales_gross), "sales_vat": cents(sales_vat),
            "refunds_gross": cents(refund_gross), "refunds_vat": cents(refund_vat),
            "net_sales": cents(net_sales), "food_cost": cents(food_cost), "gross_profit": cents(gross_profit),
            "gross_margin_percent": round(float(gross_profit / net_sales * 100), 1) if net_sales else None,
            "stock_written_off": cents(wastage), "profit_after_write_offs": cents(gross_profit - wastage),
            "bills_paid": len(order_ids),
        },
        "vat": {
            "rates": [{"rate": rate, "gross": cents(v["gross"]), "vat": cents(v["vat"]), "net": cents(v["gross"] - v["vat"])}
                      for rate, v in sorted(by_rate.items())],
            "sales_vat": cents(sales_vat), "credit_note_vat": cents(refund_vat), "vat_due": cents(sales_vat - refund_vat),
            "sales_without_rate": cents(unknown_rate),
        },
        "carwash": {"revenue": cents(wash), "note": "Car wash prices have no VAT rate recorded in the system."},
        "items": sorted(({"item": name, "quantity": v["quantity"], "gross": cents(v["gross"]), "net": cents(v["gross"] - v["vat"]),
                          "food_cost": cents(v["cost"]), "gross_profit": cents(v["gross"] - v["vat"] - v["cost"]),
                          "units_without_cost": v["no_cost"]} for name, v in items.items()),
                         key=lambda r: (-r["gross_profit"], r["item"])),
        "notes": {
            "units_without_cost": sum(v["no_cost"] for v in items.values()),
            "estimated_cost_lines": len(estimated_lines),
        },
    }
