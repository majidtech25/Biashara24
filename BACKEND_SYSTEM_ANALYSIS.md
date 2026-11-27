# Backend system analysis — 1 October 2026

## Executive assessment

Implementation update: this document records the original audit. The subsequent restaurant implementation, verification results and remaining scope are documented in [BACKEND_IMPLEMENTATION_HANDOVER.md](BACKEND_IMPLEMENTATION_HANDOVER.md).

Biashara360 has a working, database-backed core for a single restaurant: account access, menu and table setup, waiter-owned bills, additions, reviewed removals, department kitchen tickets, full cash/manual cashless settlement, manual stock movements and confirmed-revenue reporting.

It is not yet a complete restaurant operations backend. The principal missing links are kitchen production tracking, stock consumption tied to recipes and sales, payment exception handling, cashier shift accountability, durable printer recovery, and persistent support for the frontend preview modules. The existing core should be extended rather than replaced.

Readiness judgement: suitable for controlled workflow testing; not yet ready to declare complete for unattended day-to-day business operation. A passing suite demonstrates the implemented contracts, not coverage of absent business processes.

## Scope and verification

- Reviewed the active FastAPI routers, Pydantic schemas, SQLAlchemy models, transaction services, reporting, authentication, migration and backup utilities, frontend route dependencies, and backend tests.
- Executed the full existing suite: **48 passed; 95.28% statement coverage**. Results: [backend/backend-audit-tests.txt](backend/backend-audit-tests.txt).
- Ran additional probes against a newly created disposable SQLite database: [probe script](backend/audit_probe.py), [observations](backend/backend-audit-probes.json).
- Did not modify production/business records or implement new business logic. Only this report, audit verification script and generated verification files were added/updated for this analysis.
- Physical printers, payment-provider connectivity, deployment infrastructure, PostgreSQL concurrency, peak-load performance and disaster recovery on real hardware were not verified. This is a code and local-test audit, not a tax/legal certification or a penetration test.

## 1. Current architecture

FastAPI exposes authenticated APIs, SQLAlchemy stores relational records, and Pydantic validates requests. SQLite is the default; PostgreSQL can be configured. Authentication uses bcrypt passwords and JWT access/refresh tokens. The frontend calls the APIs directly and polls operational data; there is no persistent notification/event delivery system or worker-backed job processing in the inspected code.

Authoritative logic resides largely in `routes/*.py`, `services/bill_workflow.py`, `services/bill_lock.py`, `services/report_services.py` and `utils/tax.py`. Some other service files are minimal helpers or placeholders; their filenames do not establish implemented capabilities.

Order creation/addition uses server menu prices, line price/tax snapshots, idempotency records, database transactions and optimistic bill versions. SQLite bill mutations take a writer lock using `BEGIN IMMEDIATE`; table reservations and submissions have database uniqueness constraints. Printer network calls occur after the bill commit.

## 2. Capability matrix

| Business area | Implemented | Partial or absent |
|---|---|---|
| Accounts and permissions | Six roles; one sign-in page that opens the workspace for the account's role; server authorization; waiter ownership; staff creation/update; deactivation; token invalidation on account changes/logout | Kitchen-specific account/department permissions; self-service password change/recovery; rate limiting; session/device management; shift attendance |
| Menu | Create/edit food, price, category, department, availability, description, URL/uploaded image; live menu excludes inactive food/categories/departments | Modifier groups, variants, ingredient/allergen data, recipe links, scheduled menus, automatic sold-out rules; category/department edit/deactivate APIs |
| Table service | Add tables; activate/deactivate; one active bill per table; owner visibility; reservation released on cancellation/confirmed settlement | Transfers between tables/waiters, merge/split bills, guest counts, floor sections, reservations; takeaway/delivery order types |
| Ordering | Multiple lines; quantities; notes; server totals; immutable submission batches; price/tax snapshots; safe create/add retries; FIFO listing; pagination | Hold/fire courses, per-item modifiers, line preparation state, served state, stock reservation/consumption |
| Bill corrections | Waiter removal/cancellation requests; reason; manager approval/rejection; version checks; audit; retained voided lines; correction tickets | Discounts, complimentary items, promotions, post-payment refunds/credit notes, item exchanges, discretionary price overrides |
| Kitchen | Department routing; original/addition/correction tickets; batch records; whole-bill status transitions | Accept/preparing/ready/served per line or batch; measured preparation times; department-owned work queues; kitchen roles; alert escalation |
| Printers | Private-LAN ESC/POS TCP sends; destination configuration; timeout; sent/uncertain/not-configured records; no automatic replay of uncertain sends | Worker/outbox recovery, acknowledged reprint with reason, device health, queue administration, print attempts/history; physical testing |
| Payments | Full bill amount validation; one payment per bill; cash confirmation; pending manual cashless references; confirmation; locks against edits; release table; reference check within restaurant payments | Split/partial/tender-mixed payments; tips; deposits; recorded cash tender/change; rejected/wrong pending payment correction; refunds; provider integration |
| Cashier accountability | Daily cash/cashless totals; audit actor for payment entry; verifier on confirmed payment | Shift open/close, opening float, cash movements, handover, counted-versus-expected reconciliation, supervisor approval, shift-scoped reporting |
| VAT and receipts | Fixed 16% inclusive VAT; Decimal extraction/rounding; line tax snapshots; total remains entered gross price; receipt identifiers | Durable complete receipt/invoice snapshot; tax period summaries; extensible tax codes; credit notes; eTIMS integration |
| Stock | Ingredients; opening stock; manual add/adjust/deduct; insufficient-stock rejection; compare-and-update conflict checks; movement ledger; low-stock queries; usage summary | Recipes/BOM, unit conversion, automated usage, receiving documents, suppliers/purchase orders, inventory count approval, expiry/batches, wastage categories and food cost accounting |
| Reports | Daily/weekly/monthly confirmed receipts; restaurant/carwash comparison; payment-method totals; top items; current stock alerts; CSV/PDF exports; Nairobi business-day windows | Gross/net/VAT breakdowns; margins/cost of goods; refunds/discount reporting; cashier/shift reconciliation; kitchen timings; waiter performance; branches; scheduled reporting |
| Audit | Actor/IP/time and before/after values for selected bill, stock, payment and wash actions; director read access | Coverage for user/menu/category/department/printer administration and auth activity; search/date filters/pagination beyond latest 200; stronger retention/tamper controls |
| Notifications/settings | Frontend designs/previews | Persistent notification records/read states, event triggers, branch/business settings, branding/receipt settings APIs |
| Car wash | Bays/services create/list; transactions; service-price checks; manual cashless confirmation; history and summaries | Bay occupancy/reservation, attendant assignment, wash lifecycle separate from payment, edit/deactivate APIs, duplicate receipt protection, retry idempotency |
| Operations | Health response; configurable CORS; production secret validation; development-only seed creation; additive SQLite migrations with backup; backup/restore utility with integrity check | Database readiness checks, scheduled/offsite backups, restore drills, migration tooling for existing PostgreSQL, monitoring/alerts, deployment/runbooks and capacity testing |

Sources: [orders](backend/app/routes/orders.py), [bill workflow](backend/app/services/bill_workflow.py), [payments](backend/app/routes/payments.py), [stock](backend/app/routes/stock.py), [administration](backend/app/routes/admin.py), [reporting](backend/app/services/report_services.py), [car wash](backend/app/routes/carwash.py).

## 3. What currently works from end to end

1. A manager/director creates staff, categories, departments, menu items and tables.
2. A waiter selects an active free table and sends menu item IDs/quantities. The server validates availability, calculates prices, reserves the table and saves the bill/batch/submission key atomically.
3. The server routes the batch to configured department printers after commit. A missing or failing printer does not erase the order. An uncertain request retry retrieves the existing bill without printing the batch again.
4. The waiter can add items to the same bill using its version and a new idempotency key. Old prices and original opening time remain intact; additions create separate batches.
5. A submitted item reduction or cancellation is requested with a reason. Managers approve/reject, original quantities remain recorded, and pending requests block payment.
6. A cashier records the exact total. Cash closes the bill immediately; cashless entries remain pending manual verification and keep the table occupied. Confirmed settlement releases the table.
7. Reports include confirmed receipts by confirmation date. Stock records can be adjusted manually, but selling food does not alter ingredient balances.

Important distinctions: `TableReservation` represents an occupied table, not a future guest booking. `printed` is a whole-order workflow status, not proof that paper emerged from a printer. `ready` exists on order items but has no implemented line-level workflow. Daily revenue is confirmed gross receipt value, not profit or cash-drawer reconciliation.

## 4. Concrete defects and operational risks

### A. Pending-payment recovery is missing — high priority

Recording a pending cashless reference locks the bill. The API can verify it, but has no reject/void/correct route. A mistyped reference or receipt that cannot be verified leaves the cashier with no supported recovery flow. The probe confirmed the locked state and absence of a delete route; simply adding deletion would be the wrong solution.

Implement auditable payment attempts: pending, confirmed, rejected/voided; supervisor reason and permissions; explicit bill unlocking when no valid settlement remains. Preserve the original attempt. Add separate refund/credit-note records for already-confirmed payments.

### B. Stock and wash retries can duplicate business effects — high priority

The probe submitted the same 5 kg receiving payload twice: balance became 5 kg then 10 kg. Order submission idempotency is good, but it does not extend to stock movements or wash creation. Cash payment duplicates are blocked rather than replayed as a successful response.

Add operation-scoped idempotency keys and stored request fingerprints/results to receiving, adjustments, wash creation and settlement. Network retries should retrieve the existing result; changing a payload under the same key should conflict.

### C. Receipt-reference protection is incomplete — high priority if both businesses share collections

Restaurant payments check duplicate cashless references in application code, but the reference has no database unique constraint. SQLite's serialized bill writes reduce the race within restaurant payments; equivalent cross-order PostgreSQL behavior is not established. Wash creation performs no corresponding check. The probe created two wash entries using the same reference already attached to a restaurant payment.

Introduce a shared external-receipt registry scoped to the collecting business account/provider, with database uniqueness and controlled allocation to bills. If one external receipt legitimately covers multiple bills, track the receipt's remaining allocatable amount rather than either duplicating it or universally rejecting all reuse.

### D. Historical names/routing are not fully snapshotted — high priority

Prices/tax rates and batch payloads are snapshotted. However, the general order response and top-item report use the current menu name; correction routing uses the current menu department. The probe renamed a food and observed the old bill's item name change while the saved original batch retained its original name.

Persist item name, department, unit, pricing/tax treatment and receipt identity at submission. Use snapshots for receipts and corrections. Preserve names/addresses relevant to issued receipts independently of later staff/business edits.

### E. Kitchen and payment lifecycles are coupled — operational limitation

One bill-wide status currently represents pending/printed/ready/payment_pending/cleared/completed. Adding a new course resets the entire bill to pending. Payment clears a bill even when food preparation might still be underway. This is inadequate for staggered courses or prepaid orders.

Separate bill/settlement state from kitchen batch/line states. Keep table-release policy explicit. Add accepted/preparing/ready/served timestamps and aggregate the kitchen queue from unfinished lines, not payment state. Whole-bill status history exists, but does not provide these semantics.

### F. Printer jobs have no recovery service — operational limitation

The implementation deliberately avoids duplicate printing after ambiguous failures. This is a useful safeguard. However, synchronous network sending can delay requests, a crash after commit can leave queued/uncertain jobs, and there is no operator reprint/resolution endpoint or background recovery worker.

Use a transactional outbox with stable ticket IDs and attempt history. Give managers controlled reprint/acknowledge actions with reasons and a visible possible-duplicate warning. Sending bytes must remain distinct from confirmed physical output. Verify real printer encodings, cuts, department separation and power/network failures on site.

### G. Money storage and request validation need hardening

Order arithmetic/VAT use Decimal at calculation boundaries, but menu, order, payment and stock cost columns are Float. Other reporting paths sum floats then round. Use integer minor units or fixed-precision Numeric consistently, with a documented rounding policy and a tested data migration.

Update schemas accept explicit null for some non-null columns; handlers directly assign submitted values. Reject null for required business fields rather than relying on database errors. Enforce string limits consistently, require reasons for manual stock changes, validate complete date ranges, and test duplicate line handling and total quantity limits. Retain regression tests for aliases/dependency deprecation warnings already emitted by the suite.

### H. Administration and access controls need completion

Menu/staff changes do not call the general audit recorder. There is no dedicated cook/kitchen permission set; managers drive preparation transitions. No account lockout/rate limiter or password recovery/change-current-password workflow was found. Staff administration can reset passwords, which is a different capability.

Add action-level audit coverage, rate limits, least-privilege kitchen access and account lifecycle policies. Protect against removal/demotion of the last usable director. Do not confuse enabled staff accounts with actual staff on duty. Production mode suppresses new demo seeding but does not remove existing demo accounts; provisioning must explicitly review them.

### I. Upload validation checks signatures, not full image validity

The probe uploaded bytes beginning with a PNG signature but containing no valid image and received HTTP 201. Existing upload access control, format allowlist and size limit are useful but insufficient for image integrity.

Decode and validate images; cap dimensions, normalise metadata/encoding, add request-size/upload limits and a retention policy for orphaned images. Uploaded image storage is database-backed and grows the database/backups. Avoid adding an unrestricted server-side external-image fetcher.

### J. Deployment and scaling are not verified

`/health` returns a static success response; it does not establish database readiness or printer/payment health. Existing SQLite migrations add missing columns but are not a general constraint/type migration framework; `create_all` does not retrofit all existing table constraints. Existing non-SQLite upgrades intentionally fail when missing columns are detected.

Implement versioned migrations, readiness probes, structured request/error monitoring, backup schedules and recovery drills. Benchmark open-order queries/serialization and report generation: they perform repeated related-record and per-day queries. Measure before promising a concurrent-user capacity. High statement coverage is not a load, PostgreSQL or hardware certification.

## 5. Missing business processes required for smoother restaurant operations

### Kitchen and service

- Department-scoped kitchen users and queue APIs.
- Accept/preparing/ready/served per submission or line, with quantities and timestamps.
- Waiter pickup/ready notifications and acknowledgement.
- Controlled table/waiter transfer, with audit and unchanged price history.
- Explicit takeaway/delivery order types if offered; current order creation requires a table.
- Optional later: seat/course handling, reservations, modifiers and customer delivery tracking.

### Inventory and purchasing

- Recipe/BOM versions linking portions sold to ingredients and units, with unit conversions.
- Choose the stock-consumption event: accepted production, preparation start or another documented point. Prevent consumption from running twice on retries.
- Distinguish cancellation before preparation from prepared-food waste; do not automatically restore stock for food already consumed.
- Supplier, purchase request/order, receiving document and delivery-line records; partial receipts and supplier returns.
- Stock count sessions with expected/counted/variance, review and one atomic posting operation.
- Categorised wastage, expiry/batch tracking if needed, stock costs and menu margin reports.
- Explicit policy for negative stock and automatic sold-out availability.

### Cash office

- Cashier shifts, opening float, till movements, close/reopen permissions and cash handover.
- Recorded tendered amount/change; expected and counted drawer totals; supervisor reconciliation.
- Pending cashless exception handling, settlement retry safety, refund/credit-note workflows.
- Split bills/tenders and partial payments if required by the restaurant's service policy.
- Provider integration only when needed; current M-Pesa wording describes manual receipt bookkeeping, not an API integration.

### Management and records

- Persisted business settings, receipt details, timezone/cutoff and optional branch scoping.
- Notification events/inbox/read states with role/ownership checks.
- Staff shift activity and operational timings before displaying performance metrics.
- Sales, confirmed receipts, VAT, discounts, refunds, stock cost and profit reports with clearly defined meanings.
- Durable invoice/receipt/credit-note snapshots and a separately scoped eTIMS integration project. Fixed 16% arithmetic alone does not constitute tax-system integration or establish compliance.

## 6. Frontend-to-backend gap map

| Current frontend preview | Required backend records/actions |
|---|---|
| Branches | Branch entities, membership and query scoping; migration of existing records to a main branch |
| Settings | Business settings with validation, update permission, version history and receipt snapshots |
| Notifications | Event producers, notification records, recipient/role targeting and read state |
| Suppliers | Supplier contacts, active state, history and links to purchase/receiving records |
| Deliveries/reorder | Purchase documents/lines, statuses, approval, partial receiving and idempotent posting |
| Recipes | Menu-to-ingredient quantities, yields, units and versioned consumption rules |
| Stock counts | Count sessions/lines, variances, reviewer decision and atomic adjustment posting |
| Reconciliation | Shift/till ownership, opening float, movements, counted close and approval |
| Attendants/bay board | Attendant assignment, bay reservation and wash lifecycle independent of payment |
| Category/department/bay/service edit previews | Validated update/deactivate routes, dependency/occupancy checks and audit |

Preview records are not a source of live business truth and should not be automatically migrated into real accounts, payments or stock.

## 7. Recommended implementation order and acceptance criteria

| Phase | Deliverables | Acceptance gate |
|---|---|---|
| 1 — Protect transactions | Payment correction/rejection, receipt uniqueness/allocation, idempotent stock/payment/wash writes, full snapshots, validation and audit | Concurrent requests and retries cannot duplicate money, stock or tickets; bad pending entries can be resolved without deleting history |
| 2 — Kitchen/service | Kitchen roles, batch/line lifecycle, ready/served events, printer outbox/operator recovery, transfers | Two departments can progress independently; additions do not reset served food; network failures do not lose orders or silently reprint |
| 3 — Stock integration | Recipes/units, controlled usage, receiving documents, wastage, stock counts and purchasing | A sale consumes the correct ingredients exactly once; pre/post-preparation cancellations follow the agreed stock policy |
| 4 — Cashier close | Shift/till model, tender/change records, refunds/credits, reconciliation and immutable receipts | Opening float + cash movements + receipts - refunds equals expected cash; counted differences require a reason/review |
| 5 — Management integration | Settings, notifications, relevant frontend preview APIs, report refinements; branch support if actually needed | Every operational screen has a defined data contract and permissions; reported values reconcile with ledgers |
| 6 — Deployment acceptance | Migrations, monitoring, backups/restore, target-database races, hardware and peak-load tests; tax/provider integration as scoped | A full opening-to-closing-day rehearsal, failure/recovery rehearsal and restore drill pass |

For a single restaurant, branch management, loyalty, advanced reservations and payroll should not delay fixing payment recovery, kitchen flow, stock consumption and cashier reconciliation.

## 8. Target day-in-the-life acceptance run

1. Open cashier shift and verify float; staff sign in under appropriate roles.
2. Receive ingredients; confirm recipe costs/availability and printer readiness.
3. Two waiters attempt the same table; exactly one bill reserves it.
4. Send food/drinks to different departments; repeat a request after a simulated timeout; exactly one submission and intended stock effect exist.
5. Mark drinks ready while food is still preparing; notify the correct waiter; serve items independently.
6. Add another course without changing old prices, served states or original timestamps.
7. Correct a quantity; require approval; route the correction and apply the correct waste/restock policy.
8. Enter a wrong cashless reference; reject/correct it with an audit trail; then settle accurately. Exercise cash/change and any agreed split-tender policy.
9. Confirm receipt history remains unchanged after menu/staff/settings edits; ensure table release follows the service policy.
10. Close and reconcile the till, verify stock movements and sales/VAT reports, then restore a backup into a separate environment.

## Evidence index

- [Authentication and permission enforcement](backend/app/middleware/auth.py), [auth endpoints](backend/app/routes/auth.py)
- [Bills/tables](backend/app/routes/orders.py), [bill transactions](backend/app/services/bill_workflow.py), [locking](backend/app/services/bill_lock.py)
- [Order/price models](backend/app/models/order.py), [submission and ownership models](backend/app/models/waiter.py)
- [Payments](backend/app/routes/payments.py), [payment constraints](backend/app/models/payment.py)
- [Menu/staff configuration](backend/app/routes/admin.py), [image upload](backend/app/routes/menu_images.py), [schema validation](backend/app/schemas.py)
- [Stock](backend/app/routes/stock.py), [stock models](backend/app/models/stock.py)
- [Printer transport](backend/app/services/printers_services.py), [audit recorder](backend/app/services/audit.py)
- [VAT](backend/app/utils/tax.py), [order serialisation](backend/app/utils/helpers.py), [reports](backend/app/services/report_services.py)
- [Car wash](backend/app/routes/carwash.py), [migration](backend/app/migrations.py), [backup/restore](backend/app/ops.py), [startup/health](backend/app/main.py)
- [Existing integration tests](backend/tests/test_integration.py), [bill concurrency tests](backend/tests/test_waiter_phase2.py), [menu/tax tests](backend/tests/test_menu_tax.py)
