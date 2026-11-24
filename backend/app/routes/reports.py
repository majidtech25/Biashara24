from ..utils.helpers import business_today
import csv
import io
from datetime import date, timedelta
from typing import Literal
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
from ..database import get_db
from ..middleware.auth import require_roles
from ..services.report_services import build, daily_data, pdf_document, profit_vat

router = APIRouter(prefix="/api/reports", tags=["Reports"])
auth = require_roles("manager", "director")

@router.get("/daily")
def daily(day: date | None = None, date_value: date | None = Query(None, alias="date"), db: Session = Depends(get_db), _=Depends(auth)):
    chosen = date_value or day or business_today()
    return {**build(db, chosen, chosen), **daily_data(db, chosen)}

@router.get("/weekly")
def weekly(week_start: date | None = None, end_date: date | None = None, db: Session = Depends(get_db), _=Depends(auth)):
    first = week_start or ((end_date or business_today()) - timedelta(days=6))
    return build(db, first, first + timedelta(days=6))

@router.get("/monthly")
def monthly(year: int | None = Query(None, ge=2000, le=2100), month: int | None = Query(None, ge=1, le=12),
            db: Session = Depends(get_db), _=Depends(auth)):
    year, month = year or business_today().year, month or business_today().month
    first = date(year, month, 1)
    last = (date(year+1, 1, 1) if month == 12 else date(year, month+1, 1)) - timedelta(days=1)
    return build(db, first, last)

@router.get("/profit-vat")
def profit_and_vat(from_date: date | None = None, to_date: date | None = None, db: Session = Depends(get_db), _=Depends(auth)):
    """Restaurant sales without VAT, food cost, gross profit, and VAT by rate for a date range."""
    last = to_date or business_today()
    return profit_vat(db, from_date or last.replace(day=1), last)

@router.get("/export")
def export(report_type: Literal["daily", "weekly", "monthly"] = "daily", format: Literal["csv", "pdf"] = "csv",
           from_date: date | None = None, to_date: date | None = None,
           start_date: date | None = None, end_date: date | None = None,
           db: Session = Depends(get_db), _=Depends(auth)):
    last = to_date or end_date or business_today()
    first = from_date or start_date or (last if report_type == "daily" else last-timedelta(days=6) if report_type == "weekly" else last.replace(day=1))
    data = build(db, first, last)
    if format == "csv":
        stream = io.StringIO(); writer = csv.writer(stream)
        writer.writerow(["Date", "Restaurant", "Car wash", "Total", "Restaurant cash", "Restaurant M-Pesa", "Car wash cash", "Car wash M-Pesa", "Orders", "Washes"])
        for row in data["days"]:
            writer.writerow([row[k] for k in ("date", "restaurant", "carwash", "total", "restaurant_cash", "restaurant_mpesa", "carwash_cash", "carwash_mpesa", "orders_count", "washes_count")])
        writer.writerow(["TOTAL", data["totals"]["restaurant"], data["totals"]["carwash"], data["totals"]["combined"]])
        writer.writerow([]); writer.writerow(["Top item", "Quantity", "Revenue"])
        for row in data["top_items"]: writer.writerow([safe_cell(row["item"]), row["quantity"], row["revenue"]])
        writer.writerow([]); writer.writerow(["Current low stock (not historical)", "Quantity", "Minimum", "Unit"])
        for row in data["stock"]["low_items"]: writer.writerow([safe_cell(row["ingredient"]), row["current"], row["min"], safe_cell(row["unit"])])
        content = stream.getvalue(); media = "text/csv"
    else:
        lines = ["Biashara360 - Confirmed receipts report", f"{first} to {last}", "Amounts in KES",
                 "Date | Restaurant | Car wash | Total | Orders | Washes"]
        lines += [f'{r["date"]} | {r["restaurant"]:.2f} | {r["carwash"]:.2f} | {r["total"]:.2f} | {r["orders_count"]} | {r["washes_count"]}' for r in data["days"]]
        lines += ["", "Payment methods by day (restaurant cash / M-Pesa; car wash cash / M-Pesa)"]
        lines += [f'{r["date"]} | {r["restaurant_cash"]:.2f} / {r["restaurant_mpesa"]:.2f}; {r["carwash_cash"]:.2f} / {r["carwash_mpesa"]:.2f}' for r in data["days"]]
        lines += ["", f'Total restaurant: {data["totals"]["restaurant"]:.2f}', f'Total car wash: {data["totals"]["carwash"]:.2f}',
                  f'Combined: {data["totals"]["combined"]:.2f}', "", "Top selling items"]
        lines += [f'{r["item"][:50]} | {r["quantity"]} | {r["revenue"]:.2f}' for r in data["top_items"]]
        lines += ["", "Current low stock (not historical)"]
        lines += [f'{r["ingredient"][:45]} | {r["current"]} {r["unit"]} | minimum {r["min"]}' for r in data["stock"]["low_items"]]
        content = pdf_document(lines); media = "application/pdf"
    return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="biashara360-{first}-{last}.{format}"'})

def safe_cell(value):
    value = str(value)
    return "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value
