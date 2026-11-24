-- SQLite database created by the app at schema version 6 (before Alembic and branches),
-- with one menu item, table, open bill and ingredient. Used by test_upgrade_real_v6_database.
BEGIN TRANSACTION;
CREATE TABLE audit_logs (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	action VARCHAR(80) NOT NULL, 
	module VARCHAR(50) NOT NULL, 
	entity_type VARCHAR(50) NOT NULL, 
	entity_id INTEGER NOT NULL, 
	old_values JSON, 
	new_values JSON, 
	ip_address VARCHAR(80), 
	timestamp DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
INSERT INTO "audit_logs" VALUES(1,1,'create','categories','categories',3,'null','{"id": 3, "name": "Food X", "description": null, "is_active": true}','testclient','2026-11-24 11:20:20.531377');
INSERT INTO "audit_logs" VALUES(2,1,'create','departments','departments',4,'null','{"id": 4, "name": "Kitchen X", "printer_ip": null, "printer_port": 9100, "is_active": true}','testclient','2026-11-24 11:20:20.542501');
INSERT INTO "audit_logs" VALUES(3,1,'create','menu','menu',1,'null','{"id": 1, "name": "Pilau", "price": 116.1, "category_id": 3, "department_id": 4, "image_url": null, "description": null, "tax_rate": 16, "active": true}','testclient','2026-11-24 11:20:20.553154');
INSERT INTO "audit_logs" VALUES(4,1,'create','tables','tables',1,'null','{"number": 5, "is_active": true}','testclient','2026-11-24 11:20:20.567217');
INSERT INTO "audit_logs" VALUES(5,1,'create_bill','orders','orders',1,'null','{"table": 5, "batch_id": 1, "total": 348.3}','testclient','2026-11-24 11:20:20.590506');
INSERT INTO "audit_logs" VALUES(6,1,'create','ingredients','ingredients',1,'null','{"name": "Rice", "current_stock": 4.0}','testclient','2026-11-24 11:20:20.609565');
CREATE TABLE bill_change_requests (
	id INTEGER NOT NULL, 
	order_id INTEGER NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	items JSON NOT NULL, 
	reason TEXT NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	requested_by INTEGER NOT NULL, 
	decided_by INTEGER, 
	decision_reason TEXT, 
	created_at DATETIME NOT NULL, 
	decided_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(order_id) REFERENCES orders (id), 
	FOREIGN KEY(requested_by) REFERENCES users (id), 
	FOREIGN KEY(decided_by) REFERENCES users (id)
);
CREATE TABLE bill_submissions (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	"key" VARCHAR(100) NOT NULL, 
	fingerprint VARCHAR(64) NOT NULL, 
	order_id INTEGER NOT NULL, 
	batch_id INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_bill_submission_user_key UNIQUE (user_id, "key"), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(order_id) REFERENCES orders (id), 
	FOREIGN KEY(batch_id) REFERENCES order_batches (id)
);
INSERT INTO "bill_submissions" VALUES(1,1,'5b11a49121f94e38a55bb99247be6743','bdc93d8149fc27911443d002d69b2b1be1e6bde3682e59aae712815252149457',1,1);
CREATE TABLE business_settings (
	id INTEGER NOT NULL, 
	version INTEGER NOT NULL, 
	"values" JSON NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE carwash_bays (
	id INTEGER NOT NULL, 
	bay_number INTEGER NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (bay_number)
);
CREATE TABLE carwash_services (
	id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description TEXT, 
	price FLOAT NOT NULL, 
	duration_minutes INTEGER NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);
CREATE TABLE carwash_transactions (
	id INTEGER NOT NULL, 
	transaction_number VARCHAR(40), 
	bay_id INTEGER, 
	service_id INTEGER, 
	vehicle_type VARCHAR(50), 
	mpesa_reference VARCHAR(100), 
	started_at DATETIME NOT NULL, 
	vehicle_plate VARCHAR(20) NOT NULL, 
	payment_method VARCHAR(20) NOT NULL, 
	amount FLOAT NOT NULL, 
	payment_status VARCHAR(20) NOT NULL, 
	created_by INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	completed_at DATETIME, 
	notes TEXT, 
	shift_id INTEGER, 
	service_name_at_time VARCHAR(100), 
	PRIMARY KEY (id), 
	UNIQUE (transaction_number), 
	FOREIGN KEY(bay_id) REFERENCES carwash_bays (id), 
	FOREIGN KEY(service_id) REFERENCES carwash_services (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(shift_id) REFERENCES cash_shifts (id)
);
CREATE TABLE cash_shifts (
	id INTEGER NOT NULL, 
	cashier_id INTEGER NOT NULL, 
	active_cashier_id INTEGER, 
	opening_float FLOAT NOT NULL, 
	counted_cash FLOAT, 
	expected_cash FLOAT, 
	variance_reason VARCHAR(500), 
	status VARCHAR(20) NOT NULL, 
	opened_at DATETIME NOT NULL, 
	closed_at DATETIME, 
	reviewed_by INTEGER, 
	reviewed_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(cashier_id) REFERENCES users (id), 
	UNIQUE (active_cashier_id), 
	FOREIGN KEY(reviewed_by) REFERENCES users (id)
);
CREATE TABLE categories (
	id INTEGER NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	description TEXT, 
	is_active BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);
INSERT INTO "categories" VALUES(1,'Food',NULL,1,'2026-11-24 11:20:20.247508');
INSERT INTO "categories" VALUES(2,'Drinks',NULL,1,'2026-11-24 11:20:20.247519');
INSERT INTO "categories" VALUES(3,'Food X',NULL,1,'2026-11-24 11:20:20.529728');
CREATE TABLE daily_summaries (
	id INTEGER NOT NULL, 
	summary_date DATE NOT NULL, 
	restaurant_orders_count INTEGER NOT NULL, 
	restaurant_revenue FLOAT NOT NULL, 
	restaurant_cash FLOAT NOT NULL, 
	restaurant_mpesa FLOAT NOT NULL, 
	carwash_count INTEGER NOT NULL, 
	carwash_revenue FLOAT NOT NULL, 
	carwash_cash FLOAT NOT NULL, 
	carwash_mpesa FLOAT NOT NULL, 
	low_stock_items INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (summary_date)
);
CREATE TABLE departments (
	id INTEGER NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	printer_ip VARCHAR(80), 
	printer_port INTEGER NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);
INSERT INTO "departments" VALUES(1,'Kitchen',NULL,9100,1,'2026-11-24 11:20:20.249002');
INSERT INTO "departments" VALUES(2,'Barista',NULL,9100,1,'2026-11-24 11:20:20.249049');
INSERT INTO "departments" VALUES(3,'Pastry',NULL,9100,1,'2026-11-24 11:20:20.249051');
INSERT INTO "departments" VALUES(4,'Kitchen X',NULL,9100,1,'2026-11-24 11:20:20.541982');
CREATE TABLE dining_tables (
	id INTEGER NOT NULL, 
	number INTEGER NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (number)
);
INSERT INTO "dining_tables" VALUES(1,5,1);
CREATE TABLE external_receipts (
	reference VARCHAR(100) NOT NULL, 
	source VARCHAR(20) NOT NULL, 
	source_id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (reference)
);
CREATE TABLE food_waste (
	id INTEGER NOT NULL, 
	order_item_id INTEGER NOT NULL, 
	quantity INTEGER NOT NULL, 
	reason VARCHAR(500) NOT NULL, 
	ingredients JSON NOT NULL, 
	recorded_by INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(order_item_id) REFERENCES order_items (id), 
	FOREIGN KEY(recorded_by) REFERENCES users (id)
);
CREATE TABLE ingredients (
	id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	unit VARCHAR(30) NOT NULL, 
	description TEXT, 
	reorder_quantity FLOAT NOT NULL, 
	cost_per_unit FLOAT NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	min_level FLOAT NOT NULL, 
	current_stock FLOAT NOT NULL, 
	last_updated DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);
INSERT INTO "ingredients" VALUES(1,'Rice','kg',NULL,0.0,0.0,1,1.0,4.0,'2026-11-24 11:20:20.608872','2026-11-24 11:20:20.608876');
CREATE TABLE kitchen_lines (
	order_item_id INTEGER NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	version INTEGER NOT NULL, 
	recipe_snapshot JSON NOT NULL, 
	started_at DATETIME, 
	ready_at DATETIME, 
	served_at DATETIME, 
	PRIMARY KEY (order_item_id), 
	FOREIGN KEY(order_item_id) REFERENCES order_items (id)
);
INSERT INTO "kitchen_lines" VALUES(1,'pending',1,'[]',NULL,NULL,NULL);
CREATE TABLE menu_images (
	id VARCHAR(32) NOT NULL, 
	content_type VARCHAR(30) NOT NULL, 
	content BLOB NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE menu_items (
	id INTEGER NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	price FLOAT NOT NULL, 
	category_id INTEGER NOT NULL, 
	department_id INTEGER NOT NULL, 
	image_url VARCHAR(500), 
	description VARCHAR(500), 
	tax_rate INTEGER NOT NULL, 
	updated_at DATETIME NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(category_id) REFERENCES categories (id), 
	FOREIGN KEY(department_id) REFERENCES departments (id)
);
INSERT INTO "menu_items" VALUES(1,'Pilau',116.1,3,4,NULL,NULL,16,'2026-11-24 11:20:20.552590',1,'2026-11-24 11:20:20.552594');
CREATE TABLE notifications (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	message VARCHAR(500) NOT NULL, 
	order_id INTEGER, 
	created_at DATETIME NOT NULL, 
	read_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(order_id) REFERENCES orders (id)
);
CREATE TABLE order_batches (
	id INTEGER NOT NULL, 
	order_id INTEGER NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	items JSON NOT NULL, 
	notes TEXT, 
	deliveries JSON NOT NULL, 
	created_by INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(order_id) REFERENCES orders (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);
INSERT INTO "order_batches" VALUES(1,1,'original','[{"order_item_id": 1, "menu_item_id": 1, "name": "Pilau", "quantity": 3, "unit_price": 116.1, "department_id": 4, "department_name": "Kitchen X"}]',NULL,'[{"department_id": 4, "department": "Kitchen X", "status": "not_configured"}]',1,'2026-11-24 11:20:20.589852');
CREATE TABLE order_items (
	id INTEGER NOT NULL, 
	order_id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	menu_item_id INTEGER NOT NULL, 
	quantity INTEGER NOT NULL, 
	voided_quantity INTEGER NOT NULL, 
	price_at_time FLOAT NOT NULL, 
	tax_rate_at_time INTEGER, 
	name_at_time VARCHAR(120), 
	department_id_at_time INTEGER, 
	department_name_at_time VARCHAR(80), 
	ready BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE CASCADE, 
	FOREIGN KEY(menu_item_id) REFERENCES menu_items (id), 
	FOREIGN KEY(department_id_at_time) REFERENCES departments (id)
);
INSERT INTO "order_items" VALUES(1,1,'2026-11-24 11:20:20.585513',1,3,0,116.1,16,'Pilau',4,'Kitchen X',0);
CREATE TABLE order_status_history (
	id INTEGER NOT NULL, 
	order_id INTEGER NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	changed_by INTEGER NOT NULL, 
	changed_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE CASCADE, 
	FOREIGN KEY(changed_by) REFERENCES users (id)
);
INSERT INTO "order_status_history" VALUES(1,1,'pending',1,'2026-11-24 11:20:20.590948');
CREATE TABLE orders (
	id INTEGER NOT NULL, 
	table_id INTEGER, 
	version INTEGER NOT NULL, 
	order_number VARCHAR(40) NOT NULL, 
	waiter_id INTEGER NOT NULL, 
	customer VARCHAR(120), 
	notes TEXT, 
	updated_at DATETIME NOT NULL, 
	total FLOAT NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	created_at DATETIME NOT NULL, 
	cleared_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(table_id) REFERENCES dining_tables (id), 
	FOREIGN KEY(waiter_id) REFERENCES users (id)
);
INSERT INTO "orders" VALUES(1,1,1,'B261124-716D59',1,NULL,NULL,'2026-11-24 11:20:20.589310',348.3,'pending','2026-11-24 11:20:20.578132',NULL);
CREATE TABLE payments (
	id INTEGER NOT NULL, 
	order_id INTEGER NOT NULL, 
	active_order_id INTEGER, 
	amount FLOAT NOT NULL, 
	method VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	notes VARCHAR(500), 
	verified_by INTEGER, 
	reference VARCHAR(100), 
	created_at DATETIME NOT NULL, 
	completed_at DATETIME, 
	rejected_at DATETIME, 
	rejected_by INTEGER, 
	rejection_reason VARCHAR(500), 
	receipt_snapshot JSON, 
	shift_id INTEGER, 
	recorded_by INTEGER, 
	tendered_amount FLOAT, 
	change_amount FLOAT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(order_id) REFERENCES orders (id), 
	UNIQUE (active_order_id), 
	FOREIGN KEY(verified_by) REFERENCES users (id), 
	FOREIGN KEY(rejected_by) REFERENCES users (id), 
	FOREIGN KEY(shift_id) REFERENCES cash_shifts (id), 
	FOREIGN KEY(recorded_by) REFERENCES users (id)
);
CREATE TABLE recipes (
	id INTEGER NOT NULL, 
	menu_item_id INTEGER NOT NULL, 
	version INTEGER NOT NULL, 
	components JSON NOT NULL, 
	created_by INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (menu_item_id, version), 
	FOREIGN KEY(menu_item_id) REFERENCES menu_items (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);
CREATE TABLE refunds (
	id INTEGER NOT NULL, 
	payment_id INTEGER NOT NULL, 
	shift_id INTEGER, 
	amount FLOAT NOT NULL, 
	reason VARCHAR(500) NOT NULL, 
	reference VARCHAR(100), 
	recorded_by INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(payment_id) REFERENCES payments (id), 
	FOREIGN KEY(shift_id) REFERENCES cash_shifts (id), 
	FOREIGN KEY(recorded_by) REFERENCES users (id)
);
CREATE TABLE revoked_tokens (
	id INTEGER NOT NULL, 
	jti VARCHAR(80) NOT NULL, 
	expires_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE schema_versions (version INTEGER PRIMARY KEY);
INSERT INTO "schema_versions" VALUES(1);
INSERT INTO "schema_versions" VALUES(2);
INSERT INTO "schema_versions" VALUES(3);
INSERT INTO "schema_versions" VALUES(4);
INSERT INTO "schema_versions" VALUES(5);
INSERT INTO "schema_versions" VALUES(6);
CREATE TABLE stock_documents (
	id INTEGER NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	supplier_id INTEGER, 
	reference VARCHAR(100) NOT NULL, 
	lines JSON NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	reason VARCHAR(500) NOT NULL, 
	created_by INTEGER NOT NULL, 
	posted_by INTEGER, 
	created_at DATETIME NOT NULL, 
	posted_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(supplier_id) REFERENCES suppliers (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(posted_by) REFERENCES users (id)
);
CREATE TABLE stock_reservations (
	order_item_id INTEGER NOT NULL, 
	ingredient_id INTEGER NOT NULL, 
	quantity FLOAT NOT NULL, 
	PRIMARY KEY (order_item_id, ingredient_id), 
	FOREIGN KEY(order_item_id) REFERENCES order_items (id), 
	FOREIGN KEY(ingredient_id) REFERENCES ingredients (id)
);
CREATE TABLE stock_transactions (
	id INTEGER NOT NULL, 
	ingredient_id INTEGER NOT NULL, 
	transaction_type VARCHAR(20) NOT NULL, 
	quantity FLOAT NOT NULL, 
	quantity_before FLOAT, 
	quantity_after FLOAT, 
	reference_id INTEGER, 
	reference_type VARCHAR(40), 
	reason TEXT, 
	performed_by INTEGER NOT NULL, 
	timestamp DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(ingredient_id) REFERENCES ingredients (id), 
	FOREIGN KEY(performed_by) REFERENCES users (id)
);
INSERT INTO "stock_transactions" VALUES(1,1,'add',4.0,0.0,4.0,NULL,NULL,'Opening stock',1,'2026-11-24 11:20:20.610208');
CREATE TABLE suppliers (
	id INTEGER NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	contact VARCHAR(200) NOT NULL, 
	active BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);
CREATE TABLE table_reservations (
	table_id INTEGER NOT NULL, 
	order_id INTEGER NOT NULL, 
	PRIMARY KEY (table_id), 
	FOREIGN KEY(table_id) REFERENCES dining_tables (id), 
	UNIQUE (order_id), 
	FOREIGN KEY(order_id) REFERENCES orders (id)
);
INSERT INTO "table_reservations" VALUES(1,1);
CREATE TABLE till_movements (
	id INTEGER NOT NULL, 
	shift_id INTEGER NOT NULL, 
	amount FLOAT NOT NULL, 
	reason VARCHAR(500) NOT NULL, 
	recorded_by INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(shift_id) REFERENCES cash_shifts (id), 
	FOREIGN KEY(recorded_by) REFERENCES users (id)
);
CREATE TABLE users (
	id INTEGER NOT NULL, 
	username VARCHAR(80) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	department_id INTEGER, 
	full_name VARCHAR(120), 
	active BOOLEAN NOT NULL, 
	email VARCHAR(150), 
	phone VARCHAR(30), 
	updated_at DATETIME NOT NULL, 
	token_version INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(department_id) REFERENCES departments (id)
);
INSERT INTO "users" VALUES(1,'director@gmail.com','$2b$12$tJ1UHnbH5ydPI7gh.VaegOv6Eh3QCf7z6t.qSlEkwOL3N0Jy515fe','director',NULL,'Director',1,NULL,NULL,'2026-11-24 11:20:20.250337',0,'2026-11-24 11:20:20.250343');
INSERT INTO "users" VALUES(2,'manager@gmail.com','$2b$12$fS7vvPJydEBOWnY8D3Sy/OIDfr7/.UDTkae4/4d8bgYCo.0UX4LUS','manager',NULL,'Manager',1,NULL,NULL,'2026-11-24 11:20:20.250344',0,'2026-11-24 11:20:20.250345');
INSERT INTO "users" VALUES(3,'cashier@gmail.com','$2b$12$UBhfE/i6dMH2jk1N7.bdU.4rG/idzJIP1TH6zTMSIpce6KD1qOrRS','cashier',NULL,'Cashier',1,NULL,NULL,'2026-11-24 11:20:20.250346',0,'2026-11-24 11:20:20.250346');
INSERT INTO "users" VALUES(4,'waiter@gmail.com','$2b$12$2TTe/juUXHdL9KwuclkI1esszJivcvu0tOzh51KvFmOJBaIF.vJXW','waiter',NULL,'Waiter',1,NULL,NULL,'2026-11-24 11:20:20.250347',0,'2026-11-24 11:20:20.250348');
INSERT INTO "users" VALUES(5,'store@gmail.com','$2b$12$dTTiCmdC8c2BVjsvr2CqWOV04Q4j8rW8KK/7qMn3qNnJmNBoL26xa','store_manager',NULL,'Store Manager',1,NULL,NULL,'2026-11-24 11:20:20.250349',0,'2026-11-24 11:20:20.250350');
INSERT INTO "users" VALUES(6,'carwash@gmail.com','$2b$12$u.rkguEyCwzkgaFme3JMRuBQ8n0uk7HxBPH8TIUjIKYcnBAqDg1GW','carwash_manager',NULL,'Car Wash Manager',1,NULL,NULL,'2026-11-24 11:20:20.250350',0,'2026-11-24 11:20:20.250351');
CREATE TABLE write_submissions (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	"key" VARCHAR(100) NOT NULL, 
	fingerprint VARCHAR(64) NOT NULL, 
	response JSON, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (user_id, "key"), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE UNIQUE INDEX ix_revoked_tokens_jti ON revoked_tokens (jti);
CREATE INDEX ix_users_active ON users (active);
CREATE UNIQUE INDEX ix_users_username ON users (username);
CREATE INDEX ix_users_role ON users (role);
CREATE INDEX ix_menu_items_category_id ON menu_items (category_id);
CREATE UNIQUE INDEX ix_menu_items_name ON menu_items (name);
CREATE INDEX ix_menu_items_department_id ON menu_items (department_id);
CREATE INDEX ix_orders_created_at ON orders (created_at);
CREATE UNIQUE INDEX ix_orders_order_number ON orders (order_number);
CREATE INDEX ix_orders_waiter_id ON orders (waiter_id);
CREATE INDEX ix_orders_status ON orders (status);
CREATE INDEX ix_stock_transactions_timestamp ON stock_transactions (timestamp);
CREATE INDEX ix_stock_transactions_ingredient_id ON stock_transactions (ingredient_id);
CREATE INDEX ix_audit_logs_timestamp ON audit_logs (timestamp);
CREATE INDEX ix_audit_logs_user_id ON audit_logs (user_id);
CREATE INDEX ix_order_items_order_id ON order_items (order_id);
CREATE INDEX ix_order_status_history_order_id ON order_status_history (order_id);
CREATE INDEX ix_payments_order_id ON payments (order_id);
CREATE INDEX ix_payments_status ON payments (status);
CREATE INDEX ix_payments_method ON payments (method);
CREATE INDEX ix_payments_created_at ON payments (created_at);
CREATE INDEX ix_notifications_user_id ON notifications (user_id);
CREATE INDEX ix_carwash_transactions_payment_status ON carwash_transactions (payment_status);
CREATE INDEX ix_carwash_transactions_bay_id ON carwash_transactions (bay_id);
CREATE INDEX ix_carwash_transactions_created_at ON carwash_transactions (created_at);
CREATE INDEX ix_carwash_transactions_vehicle_plate ON carwash_transactions (vehicle_plate);
CREATE INDEX ix_order_batches_order_id ON order_batches (order_id);
CREATE INDEX ix_bill_change_requests_status ON bill_change_requests (status);
CREATE INDEX ix_bill_change_requests_order_id ON bill_change_requests (order_id);
CREATE UNIQUE INDEX ux_refund_reference ON refunds (reference);
CREATE UNIQUE INDEX ux_wash_number ON carwash_transactions(transaction_number);
COMMIT;
