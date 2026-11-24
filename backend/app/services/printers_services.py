"""Raw TCP ESC/POS tickets. Only configured department printers receive jobs."""
import ipaddress
import socket
from collections import defaultdict

def kitchen_ticket(order_number: str, department: str) -> dict:
    return {"order_number": order_number, "department": department}

def print_order(order):
    groups = defaultdict(list)
    for line in order.items:
        groups[line.menu_item.department_id].append(line)
    results = []
    for lines in groups.values():
        department = lines[0].menu_item.department
        if not department.printer_ip:
            results.append({"department": department.name, "status": "not_configured"})
            continue
        try:
            address = ipaddress.ip_address(department.printer_ip)
            if not address.is_private or address.is_loopback or address.is_unspecified:
                raise ValueError("Printer must use a private LAN address")
            text = "\n".join(["Biashara360", department.name, "Order: " + order.order_number,
                  *[f"{line.quantity} x {line.menu_item.name}" for line in lines], order.notes or "", "\n\n"])
            text = "".join(c for c in text if c == "\n" or ord(c) >= 32)
            ticket = b"\x1b@" + text.encode("cp437", errors="replace") + b"\x1dV\x00"
            with socket.create_connection((str(address), department.printer_port), timeout=3) as conn:
                conn.sendall(ticket)
            results.append({"department": department.name, "status": "sent"})
        except (OSError, ValueError) as exc:
            # A failed send may have partially printed. Do not silently retry.
            results.append({"department": department.name, "status": "failed", "detail": str(exc)})
    return results

def printer_for(db, department, branch_id):
    """(address, port) of the department's printer at this branch, or None if there is none."""
    from sqlalchemy import select
    from ..models import BranchPrinter
    if branch_id is not None:
        own = db.scalar(select(BranchPrinter).where(BranchPrinter.branch_id == branch_id, BranchPrinter.department_id == department.id))
        if own is not None:
            return own.printer_ip, own.printer_port
    return (department.printer_ip, department.printer_port) if department.printer_ip else None


def render_ticket(department, order, submission, entries, table_number) -> bytes:
    """ESC/POS bytes for one kitchen ticket."""
    label = {"original": "NEW ORDER", "addition": "ADDITIONAL ITEMS", "correction": "CORRECTION - REMOVE ITEMS"}.get(submission.kind, submission.kind.upper())
    where = f"Table: {table_number}" if table_number else ("TAKEAWAY" + (f" - {order.customer}" if order.customer else "")) if getattr(order, "order_type", None) == "takeaway" else "Table: Unassigned"
    lines = ["Biashara360", label, department.name, where,
             "Bill: " + order.order_number, "Waiter: " + (order.waiter.full_name or order.waiter.username),
             f"Ticket: {submission.id} | {submission.created_at.isoformat()} UTC"]
    lines += [f"{abs(i['quantity'])} x {i['name']}" for i in entries]
    lines += [submission.notes or "", "\n\n"]
    text = "\n".join(lines)
    text = "".join(c for c in text if c == "\n" or ord(c) >= 32)
    return b"\x1b@" + text.encode("cp437", errors="replace") + b"\x1dV\x00"


def send_batch_ticket(department, order, submission, entries, table_number, target=None):
    """Send one original/addition/correction ticket.

    "not_sent": the printer could not be reached, so nothing was printed and it is safe to
    try again. "uncertain": the connection opened but sending failed, so part of the ticket
    may have printed; only staff may authorise another copy."""
    target = target or ((department.printer_ip, department.printer_port) if department.printer_ip else None)
    if not target:
        return {"status": "not_configured"}
    try:
        address = ipaddress.ip_address(target[0])
        if not address.is_private or address.is_loopback or address.is_unspecified:
            raise ValueError("Printer must use a private LAN address")
    except ValueError as exc:
        return {"status": "failed", "detail": str(exc)}  # wrong printer address: fix the setting
    data = render_ticket(department, order, submission, entries, table_number)
    try:
        conn = socket.create_connection((str(address), int(target[1])), timeout=3)
    except OSError as exc:
        return {"status": "not_sent", "detail": str(exc)}
    try:
        with conn as stream:
            stream.sendall(data)
        return {"status": "sent"}
    except OSError as exc:
        return {"status": "uncertain", "detail": str(exc)}


RETRY_LIMIT = 5
RETRY_WINDOW_MINUTES = 30


def retry_unsent(db, now=None):
    """Background retry: send tickets whose printer could not be reached, up to RETRY_LIMIT
    times within RETRY_WINDOW_MINUTES of the order. Tickets that may have printed
    ("uncertain") are never retried here. Returns how many tickets were sent."""
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from ..models import Department, DiningTable, Order
    from ..models.waiter import OrderBatch
    from .bill_lock import start_write
    now = now or datetime.utcnow()
    sent = 0
    candidates = db.scalars(select(OrderBatch.id).where(OrderBatch.created_at >= now - timedelta(minutes=RETRY_WINDOW_MINUTES))
                            .order_by(OrderBatch.id)).all()
    for batch_id in candidates:
        for department_id in [d["department_id"] for d in (db.get(OrderBatch, batch_id).deliveries or [])
                              if d.get("status") == "not_sent" and d.get("attempts", 1) < RETRY_LIMIT]:
            start_write(db)
            batch = db.scalar(select(OrderBatch).where(OrderBatch.id == batch_id).with_for_update())
            deliveries = [dict(d) for d in batch.deliveries]
            index = next(i for i, d in enumerate(deliveries) if d["department_id"] == department_id)
            if deliveries[index].get("status") != "not_sent":
                db.commit(); continue  # someone else handled it
            order = db.get(Order, batch.order_id)
            from ..routes.print_agents import agent_branch
            if agent_branch(db, order.branch_id):
                db.commit(); continue  # the branch's print program handles its own retries
            department = db.get(Department, department_id)
            target = printer_for(db, department, order.branch_id)
            attempts = deliveries[index].get("attempts", 1) + 1
            deliveries[index] = {**deliveries[index], "status": "uncertain", "attempts": attempts, "retried_at": now.isoformat()}
            batch.deliveries = deliveries
            db.commit()  # claim before network I/O, as for the first send
            table = db.get(DiningTable, order.table_id) if order.table_id else None
            result = send_batch_ticket(department, order, batch, [i for i in batch.items if i["department_id"] == department_id],
                                       table.number if table else None, target)
            start_write(db)
            batch = db.scalar(select(OrderBatch).where(OrderBatch.id == batch_id).with_for_update())
            deliveries = [dict(d) for d in batch.deliveries]
            if deliveries[index].get("attempts") == attempts:  # not changed by an operator meanwhile
                deliveries[index].update(result); batch.deliveries = deliveries
            db.commit()
            sent += result["status"] == "sent"
    return sent
