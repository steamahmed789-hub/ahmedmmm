import os
import sys
import io
import csv
import shutil
import sqlite3
import hashlib
import secrets
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from datetime import datetime, date, timedelta
from typing import Optional, List, Tuple, Dict, Any
import customtkinter as ctk
LOW_STOCK_THRESHOLD = 10
CURRENCY = "EGP"
APP_NAME = "Detergent Warehouse Pro"
APP_VERSION = "1.0.0"
TAG_LOW_STOCK = "low_stock"
TAG_OK_STOCK = "ok_stock"
TAG_OUT_OF_STOCK = "out_of_stock"
TAG_EXPIRED = "expired"
ROLE_ADMIN = "admin"
ROLE_CASHIER = "cashier"
CATEGORIES = [
    "Detergent Powder",
    "Detergent Liquid",
    "Dish Soap",
    "Fabric Softener",
    "Bleach",
    "Stain Remover",
    "Floor Cleaner",
    "Glass Cleaner",
    "Disinfectant",
    "Other",
]
def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    if salt is None:
        salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return salt.hex() + ":" + dk.hex()
def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, hash_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
        return secrets.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False
def resource_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))
def fmt_money(value: float) -> str:
    return f"{value:,.2f} {CURRENCY}"
def fmt_qty(value: int) -> str:
    return f"{value:,}"
def fmt_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return value
def parse_int(value: str, field_name: str, allow_zero: bool = True) -> int:
    s = value.strip()
    if not s:
        raise ValueError(f"{field_name} cannot be empty.")
    try:
        n = int(s)
    except ValueError:
        raise ValueError(f"{field_name} must be a whole number.")
    if n < 0 or (not allow_zero and n == 0):
        raise ValueError(f"{field_name} must be {'non-negative' if allow_zero else 'positive'}.")
    return n
def parse_float(value: str, field_name: str) -> float:
    s = value.strip()
    if not s:
        raise ValueError(f"{field_name} cannot be empty.")
    s_norm = s.replace(",", ".")
    try:
        f = float(s_norm)
    except ValueError:
        raise ValueError(f"{field_name} must be a number.")
    if f < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    return f
def parse_date(value: str) -> Optional[str]:
    s = value.strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date().isoformat()
    except ValueError:
        raise ValueError("Date must be in YYYY-MM-DD format.")
class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._connect()
        self._create_tables()
        self._seed_defaults()

    def _connect(self) -> None:
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")

    def _create_tables(self) -> None:
        assert self.conn is not None
        c = self.conn.cursor()
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'cashier')),
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                phone TEXT,
                email TEXT,
                address TEXT,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                address TEXT,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL UNIQUE,
                barcode TEXT UNIQUE,
                product_name TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL,
                brand TEXT,
                unit TEXT NOT NULL DEFAULT 'piece',
                quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
                min_stock INTEGER NOT NULL DEFAULT 10 CHECK (min_stock >= 0),
                purchase_price REAL NOT NULL DEFAULT 0 CHECK (purchase_price >= 0),
                selling_price REAL NOT NULL DEFAULT 0 CHECK (selling_price >= 0),
                expiry_date TEXT,
                supplier_id INTEGER,
                notes TEXT,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS stock_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                movement_type TEXT NOT NULL CHECK (movement_type IN ('restock', 'sale', 'adjustment', 'return')),
                quantity_delta INTEGER NOT NULL,
                quantity_before INTEGER NOT NULL,
                quantity_after INTEGER NOT NULL,
                unit_price REAL NOT NULL DEFAULT 0,
                total_value REAL NOT NULL DEFAULT 0,
                reference TEXT,
                user_id INTEGER,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (product_id) REFERENCES products(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_number TEXT NOT NULL UNIQUE,
                customer_id INTEGER,
                user_id INTEGER NOT NULL,
                subtotal REAL NOT NULL DEFAULT 0,
                discount REAL NOT NULL DEFAULT 0,
                tax REAL NOT NULL DEFAULT 0,
                total REAL NOT NULL DEFAULT 0,
                payment_method TEXT NOT NULL DEFAULT 'cash',
                amount_paid REAL NOT NULL DEFAULT 0,
                change_given REAL NOT NULL DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (customer_id) REFERENCES customers(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS sale_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                product_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                purchase_price REAL NOT NULL,
                line_total REAL NOT NULL,
                FOREIGN KEY (sale_id) REFERENCES sales(id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
            CREATE INDEX IF NOT EXISTS idx_products_name ON products(product_name);
            CREATE INDEX IF NOT EXISTS idx_movements_product ON stock_movements(product_id);
            CREATE INDEX IF NOT EXISTS idx_movements_date ON stock_movements(created_at);
            CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(created_at);
            CREATE INDEX IF NOT EXISTS idx_sale_items_sale ON sale_items(sale_id);
            """
        )
        self.conn.commit()

    def _seed_defaults(self) -> None:
        assert self.conn is not None
        cur = self.conn.execute("SELECT COUNT(*) AS c FROM users;")
        if cur.fetchone()["c"] == 0:
            self.conn.execute(
                "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?);",
                ("admin", hash_password("admin123"), "Administrator", ROLE_ADMIN),
            )
            self.conn.execute(
                "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?);",
                ("cashier", hash_password("cashier123"), "Default Cashier", ROLE_CASHIER),
            )
            self.conn.execute(
                "INSERT INTO settings (key, value) VALUES ('store_name', 'My Detergent Warehouse');"
            )
            self.conn.execute(
                "INSERT INTO settings (key, value) VALUES ('store_phone', '');"
            )
            self.conn.execute(
                "INSERT INTO settings (key, value) VALUES ('store_address', '');"
            )
            self.conn.execute(
                "INSERT INTO settings (key, value) VALUES ('tax_rate', '0');"
            )
            self.conn.commit()

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def get_setting(self, key: str, default: str = "") -> str:
        assert self.conn is not None
        cur = self.conn.execute("SELECT value FROM settings WHERE key = ?;", (key,))
        row = cur.fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        assert self.conn is not None
        self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value;",
            (key, value),
        )
        self.conn.commit()

    def authenticate(self, username: str, password: str) -> Optional[sqlite3.Row]:
        assert self.conn is not None
        cur = self.conn.execute(
            "SELECT * FROM users WHERE username = ? AND is_active = 1;", (username,)
        )
        row = cur.fetchone()
        if row and verify_password(password, row["password_hash"]):
            return row
        return None

    def list_users(self) -> List[sqlite3.Row]:
        assert self.conn is not None
        return self.conn.execute(
            "SELECT id, username, full_name, role, is_active, created_at "
            "FROM users ORDER BY username;"
        ).fetchall()

    def add_user(self, username: str, password: str, full_name: str, role: str) -> int:
        assert self.conn is not None
        cur = self.conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?);",
            (username, hash_password(password), full_name, role),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_user(self, user_id: int, full_name: str, role: str, is_active: int) -> None:
        assert self.conn is not None
        self.conn.execute(
            "UPDATE users SET full_name = ?, role = ?, is_active = ? WHERE id = ?;",
            (full_name, role, is_active, user_id),
        )
        self.conn.commit()

    def reset_user_password(self, user_id: int, new_password: str) -> None:
        assert self.conn is not None
        self.conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?;",
            (hash_password(new_password), user_id),
        )
        self.conn.commit()

    def delete_user(self, user_id: int) -> None:
        assert self.conn is not None
        self.conn.execute("DELETE FROM users WHERE id = ?;", (user_id,))
        self.conn.commit()

    def list_suppliers(self, include_inactive: bool = False) -> List[sqlite3.Row]:
        assert self.conn is not None
        return self.conn.execute(
            "SELECT * FROM suppliers ORDER BY name;"
        ).fetchall()

    def add_supplier(self, name: str, phone: str, email: str, address: str, notes: str) -> int:
        assert self.conn is not None
        cur = self.conn.execute(
            "INSERT INTO suppliers (name, phone, email, address, notes) VALUES (?, ?, ?, ?, ?);",
            (name, phone, email, address, notes),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_supplier(self, supplier_id: int, name: str, phone: str, email: str, address: str, notes: str) -> None:
        assert self.conn is not None
        self.conn.execute(
            "UPDATE suppliers SET name=?, phone=?, email=?, address=?, notes=? WHERE id=?;",
            (name, phone, email, address, notes, supplier_id),
        )
        self.conn.commit()

    def delete_supplier(self, supplier_id: int) -> None:
        assert self.conn is not None
        self.conn.execute("DELETE FROM suppliers WHERE id = ?;", (supplier_id,))
        self.conn.commit()

    def list_customers(self) -> List[sqlite3.Row]:
        assert self.conn is not None
        return self.conn.execute(
            "SELECT * FROM customers ORDER BY name;"
        ).fetchall()

    def search_customers(self, query: str) -> List[sqlite3.Row]:
        assert self.conn is not None
        q = f"%{query.lower()}%"
        return self.conn.execute(
            "SELECT * FROM customers WHERE LOWER(name) LIKE ? OR phone LIKE ? ORDER BY name LIMIT 20;",
            (q, q),
        ).fetchall()

    def add_customer(self, name: str, phone: str, email: str, address: str, notes: str) -> int:
        assert self.conn is not None
        cur = self.conn.execute(
            "INSERT INTO customers (name, phone, email, address, notes) VALUES (?, ?, ?, ?, ?);",
            (name, phone, email, address, notes),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_customer(self, customer_id: int, name: str, phone: str, email: str, address: str, notes: str) -> None:
        assert self.conn is not None
        self.conn.execute(
            "UPDATE customers SET name=?, phone=?, email=?, address=?, notes=? WHERE id=?;",
            (name, phone, email, address, notes, customer_id),
        )
        self.conn.commit()

    def delete_customer(self, customer_id: int) -> None:
        assert self.conn is not None
        self.conn.execute("DELETE FROM customers WHERE id = ?;", (customer_id,))
        self.conn.commit()

    def list_products(
        self,
        category: Optional[str] = None,
        search: Optional[str] = None,
        low_stock_only: bool = False,
        include_deleted: bool = False,
    ) -> List[sqlite3.Row]:
        assert self.conn is not None
        sql = (
            "SELECT p.*, s.name AS supplier_name FROM products p "
            "LEFT JOIN suppliers s ON p.supplier_id = s.id WHERE 1=1"
        )
        params: List[Any] = []
        if not include_deleted:
            sql += " AND p.is_deleted = 0"
        if category and category != "All":
            sql += " AND p.category = ?"
            params.append(category)
        if search:
            sql += " AND (LOWER(p.product_name) LIKE ? OR LOWER(p.sku) LIKE ? OR LOWER(p.brand) LIKE ? OR LOWER(p.barcode) LIKE ?)"
            q = f"%{search.lower()}%"
            params.extend([q, q, q, q])
        if low_stock_only:
            sql += " AND p.quantity <= p.min_stock"
        sql += " ORDER BY p.product_name COLLATE NOCASE;"
        return self.conn.execute(sql, params).fetchall()

    def get_product(self, product_id: int) -> Optional[sqlite3.Row]:
        assert self.conn is not None
        cur = self.conn.execute("SELECT * FROM products WHERE id = ?;", (product_id,))
        return cur.fetchone()

    def find_product_by_barcode(self, barcode: str) -> Optional[sqlite3.Row]:
        assert self.conn is not None
        cur = self.conn.execute(
            "SELECT * FROM products WHERE barcode = ? AND is_deleted = 0;", (barcode,)
        )
        return cur.fetchone()

    def generate_sku(self) -> str:
        assert self.conn is not None
        cur = self.conn.execute("SELECT COUNT(*) AS c FROM products;")
        n = cur.fetchone()["c"] + 1
        return f"DET-{n:06d}"

    def add_product(self, data: Dict[str, Any], user_id: Optional[int] = None) -> int:
        assert self.conn is not None
        cur = self.conn.execute(
            """
            INSERT INTO products (
                sku, barcode, product_name, category, brand, unit,
                quantity, min_stock, purchase_price, selling_price,
                expiry_date, supplier_id, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                data["sku"],
                data.get("barcode") or None,
                data["product_name"],
                data["category"],
                data.get("brand") or None,
                data.get("unit", "piece"),
                data["quantity"],
                data["min_stock"],
                data["purchase_price"],
                data["selling_price"],
                data.get("expiry_date") or None,
                data.get("supplier_id") or None,
                data.get("notes") or None,
            ),
        )
        product_id = cur.lastrowid
        if data["quantity"] > 0:
            self._record_movement(
                product_id=product_id,
                movement_type="restock",
                delta=data["quantity"],
                unit_price=data["purchase_price"],
                reference="Initial stock",
                user_id=user_id,
                notes="Product created",
            )
        self.conn.commit()
        return product_id

    def update_product(self, product_id: int, data: Dict[str, Any]) -> None:
        assert self.conn is not None
        self.conn.execute(
            """
            UPDATE products SET
                barcode = ?, product_name = ?, category = ?, brand = ?, unit = ?,
                min_stock = ?, purchase_price = ?, selling_price = ?,
                expiry_date = ?, supplier_id = ?, notes = ?,
                updated_at = datetime('now')
            WHERE id = ?;
            """,
            (
                data.get("barcode") or None,
                data["product_name"],
                data["category"],
                data.get("brand") or None,
                data.get("unit", "piece"),
                data["min_stock"],
                data["purchase_price"],
                data["selling_price"],
                data.get("expiry_date") or None,
                data.get("supplier_id") or None,
                data.get("notes") or None,
                product_id,
            ),
        )
        self.conn.commit()

    def soft_delete_product(self, product_id: int) -> None:
        assert self.conn is not None
        self.conn.execute(
            "UPDATE products SET is_deleted = 1, updated_at = datetime('now') WHERE id = ?;",
            (product_id,),
        )
        self.conn.commit()

    def restore_product(self, product_id: int) -> None:
        assert self.conn is not None
        self.conn.execute(
            "UPDATE products SET is_deleted = 0, updated_at = datetime('now') WHERE id = ?;",
            (product_id,),
        )
        self.conn.commit()

    def _record_movement(
        self,
        product_id: int,
        movement_type: str,
        delta: int,
        unit_price: float,
        reference: str = "",
        user_id: Optional[int] = None,
        notes: str = "",
    ) -> None:
        assert self.conn is not None
        cur = self.conn.execute(
            "SELECT quantity FROM products WHERE id = ?;", (product_id,)
        )
        row = cur.fetchone()
        if row is None:
            return
        before = row["quantity"]
        after = before + delta
        if after < 0:
            raise ValueError("Stock cannot go below zero.")
        self.conn.execute(
            "UPDATE products SET quantity = ?, updated_at = datetime('now') WHERE id = ?;",
            (after, product_id),
        )
        self.conn.execute(
            """
            INSERT INTO stock_movements (
                product_id, movement_type, quantity_delta, quantity_before, quantity_after,
                unit_price, total_value, reference, user_id, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                product_id,
                movement_type,
                delta,
                before,
                after,
                unit_price,
                abs(delta) * unit_price,
                reference,
                user_id,
                notes,
            ),
        )

    def restock_product(
        self, product_id: int, quantity: int, unit_cost: float, user_id: int, notes: str = ""
    ) -> None:
        assert self.conn is not None
        try:
            self._record_movement(
                product_id=product_id,
                movement_type="restock",
                delta=quantity,
                unit_price=unit_cost,
                reference="Restock",
                user_id=user_id,
                notes=notes,
            )
            self.conn.execute(
                "UPDATE products SET purchase_price = ? WHERE id = ?;",
                (unit_cost, product_id),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def adjust_stock(
        self, product_id: int, new_quantity: int, user_id: int, reason: str = ""
    ) -> None:
        assert self.conn is not None
        cur = self.conn.execute("SELECT quantity, purchase_price FROM products WHERE id = ?;", (product_id,))
        row = cur.fetchone()
        if row is None:
            raise ValueError("Product not found.")
        delta = new_quantity - row["quantity"]
        try:
            self._record_movement(
                product_id=product_id,
                movement_type="adjustment",
                delta=delta,
                unit_price=row["purchase_price"],
                reference="Manual adjustment",
                user_id=user_id,
                notes=reason,
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def create_sale(
        self,
        user_id: int,
        items: List[Dict[str, Any]],
        customer_id: Optional[int],
        discount: float,
        tax: float,
        payment_method: str,
        amount_paid: float,
        notes: str,
    ) -> Tuple[int, str]:
        assert self.conn is not None
        if not items:
            raise ValueError("Sale must contain at least one item.")

        for it in items:
            cur = self.conn.execute("SELECT quantity, product_name FROM products WHERE id = ?;", (it["product_id"],))
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"Product ID {it['product_id']} not found.")
            if row["quantity"] < it["quantity"]:
                raise ValueError(
                    f"Insufficient stock for '{row['product_name']}'. "
                    f"Available: {row['quantity']}, requested: {it['quantity']}."
                )

        subtotal = sum(it["quantity"] * it["unit_price"] for it in items)
        total = subtotal - discount + tax
        change_given = max(0.0, amount_paid - total)
        invoice_number = self._generate_invoice_number()

        try:
            cur = self.conn.execute(
                """
                INSERT INTO sales (
                    invoice_number, customer_id, user_id, subtotal, discount, tax, total,
                    payment_method, amount_paid, change_given, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    invoice_number,
                    customer_id,
                    user_id,
                    subtotal,
                    discount,
                    tax,
                    total,
                    payment_method,
                    amount_paid,
                    change_given,
                    notes,
                ),
            )
            sale_id = cur.lastrowid
            for it in items:
                self.conn.execute(
                    """
                    INSERT INTO sale_items (
                        sale_id, product_id, product_name, quantity,
                        unit_price, purchase_price, line_total
                    ) VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        sale_id,
                        it["product_id"],
                        it["product_name"],
                        it["quantity"],
                        it["unit_price"],
                        it["purchase_price"],
                        it["quantity"] * it["unit_price"],
                    ),
                )
                self._record_movement(
                    product_id=it["product_id"],
                    movement_type="sale",
                    delta=-it["quantity"],
                    unit_price=it["unit_price"],
                    reference=f"Invoice {invoice_number}",
                    user_id=user_id,
                )
            self.conn.commit()
            return sale_id, invoice_number
        except Exception:
            self.conn.rollback()
            raise

    def _generate_invoice_number(self) -> str:
        assert self.conn is not None
        today = date.today().strftime("%Y%m%d")
        cur = self.conn.execute(
            "SELECT COUNT(*) AS c FROM sales WHERE invoice_number LIKE ?;",
            (f"INV-{today}-%",),
        )
        n = cur.fetchone()["c"] + 1
        return f"INV-{today}-{n:04d}"

    def get_sale(self, sale_id: int) -> Optional[sqlite3.Row]:
        assert self.conn is not None
        cur = self.conn.execute(
            """
            SELECT s.*, c.name AS customer_name, u.full_name AS user_name
            FROM sales s
            LEFT JOIN customers c ON s.customer_id = c.id
            LEFT JOIN users u ON s.user_id = u.id
            WHERE s.id = ?;
            """,
            (sale_id,),
        )
        return cur.fetchone()

    def get_sale_items(self, sale_id: int) -> List[sqlite3.Row]:
        assert self.conn is not None
        return self.conn.execute(
            "SELECT * FROM sale_items WHERE sale_id = ?;", (sale_id,)
        ).fetchall()

    def list_sales(self, date_from: Optional[str] = None, date_to: Optional[str] = None, limit: int = 200) -> List[sqlite3.Row]:
        assert self.conn is not None
        sql = (
            "SELECT s.*, c.name AS customer_name, u.full_name AS user_name "
            "FROM sales s LEFT JOIN customers c ON s.customer_id = c.id "
            "LEFT JOIN users u ON s.user_id = u.id WHERE 1=1"
        )
        params: List[Any] = []
        if date_from:
            sql += " AND date(s.created_at) >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND date(s.created_at) <= ?"
            params.append(date_to)
        sql += " ORDER BY s.created_at DESC LIMIT ?;"
        params.append(limit)
        return self.conn.execute(sql, params).fetchall()

    def list_movements(self, product_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None, limit: int = 300) -> List[sqlite3.Row]:
        assert self.conn is not None
        sql = (
            "SELECT m.*, p.product_name, p.sku, u.full_name AS user_name "
            "FROM stock_movements m "
            "LEFT JOIN products p ON m.product_id = p.id "
            "LEFT JOIN users u ON m.user_id = u.id WHERE 1=1"
        )
        params: List[Any] = []
        if product_id is not None:
            sql += " AND m.product_id = ?"
            params.append(product_id)
        if date_from:
            sql += " AND date(m.created_at) >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND date(m.created_at) <= ?"
            params.append(date_to)
        sql += " ORDER BY m.created_at DESC LIMIT ?;"
        params.append(limit)
        return self.conn.execute(sql, params).fetchall()

    def dashboard_stats(self) -> Dict[str, Any]:
        assert self.conn is not None
        today = date.today().isoformat()
        first_of_month = date.today().replace(day=1).isoformat()

        total_products = self.conn.execute(
            "SELECT COUNT(*) AS c FROM products WHERE is_deleted = 0;"
        ).fetchone()["c"]

        total_stock_value = self.conn.execute(
            "SELECT COALESCE(SUM(quantity * purchase_price), 0) AS v FROM products WHERE is_deleted = 0;"
        ).fetchone()["v"]

        low_stock = self.conn.execute(
            "SELECT COUNT(*) AS c FROM products WHERE is_deleted = 0 AND quantity <= min_stock;"
        ).fetchone()["c"]

        out_of_stock = self.conn.execute(
            "SELECT COUNT(*) AS c FROM products WHERE is_deleted = 0 AND quantity = 0;"
        ).fetchone()["c"]

        today_sales = self.conn.execute(
            "SELECT COUNT(*) AS c, COALESCE(SUM(total), 0) AS v FROM sales WHERE date(created_at) = ?;",
            (today,),
        ).fetchone()

        month_sales = self.conn.execute(
            "SELECT COUNT(*) AS c, COALESCE(SUM(total), 0) AS v FROM sales WHERE date(created_at) >= ?;",
            (first_of_month,),
        ).fetchone()

        profit_month = self.conn.execute(
            """
            SELECT COALESCE(SUM((si.unit_price - si.purchase_price) * si.quantity), 0) AS p
            FROM sale_items si
            JOIN sales s ON si.sale_id = s.id
            WHERE date(s.created_at) >= ?;
            """,
            (first_of_month,),
        ).fetchone()["p"]

        top_products = self.conn.execute(
            """
            SELECT p.product_name, SUM(si.quantity) AS qty, SUM(si.line_total) AS revenue
            FROM sale_items si
            JOIN sales s ON si.sale_id = s.id
            JOIN products p ON si.product_id = p.id
            WHERE date(s.created_at) >= ?
            GROUP BY p.id
            ORDER BY qty DESC
            LIMIT 5;
            """,
            (first_of_month,),
        ).fetchall()

        return {
            "total_products": total_products,
            "total_stock_value": total_stock_value,
            "low_stock": low_stock,
            "out_of_stock": out_of_stock,
            "today_sales_count": today_sales["c"],
            "today_sales_value": today_sales["v"],
            "month_sales_count": month_sales["c"],
            "month_sales_value": month_sales["v"],
            "month_profit": profit_month,
            "top_products": top_products,
        }

    def sales_by_day(self, days: int = 7) -> List[sqlite3.Row]:
        assert self.conn is not None
        start = (date.today() - timedelta(days=days - 1)).isoformat()
        return self.conn.execute(
            """
            SELECT date(created_at) AS d, COUNT(*) AS cnt, COALESCE(SUM(total), 0) AS total
            FROM sales
            WHERE date(created_at) >= ?
            GROUP BY date(created_at)
            ORDER BY d;
            """,
            (start,),
        ).fetchall()

    def backup(self, dest_path: str) -> None:
        assert self.conn is not None
        self.conn.commit()
        self.conn.close()
        try:
            shutil.copy2(self.db_path, dest_path)
        finally:
            self._connect()

    def restore(self, source_path: str) -> None:
        assert self.conn is not None
        self.conn.close()
        shutil.copy2(source_path, self.db_path)
        self._connect()


class LoginWindow(ctk.CTk):
    def __init__(self, db: Database, on_success) -> None:
        super().__init__()
        self.db = db
        self.on_success = on_success

        self.title(f"{APP_NAME} — Login")
        self.geometry("420x520")
        self.resizable(False, False)
        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("blue")

        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text=APP_NAME, font=ctk.CTkFont(size=24, weight="bold")
        ).grid(row=0, column=0, padx=20, pady=(40, 4), sticky="ew")

        ctk.CTkLabel(
            self, text=f"Version {APP_VERSION}", text_color="gray50"
        ).grid(row=1, column=0, padx=20, pady=(0, 30), sticky="ew")

        form = ctk.CTkFrame(self, corner_radius=10)
        form.grid(row=2, column=0, padx=30, pady=10, sticky="ew")
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="Username").grid(row=0, column=0, padx=12, pady=12, sticky="w")
        self.entry_username = ctk.CTkEntry(form, placeholder_text="admin", width=220)
        self.entry_username.grid(row=0, column=1, padx=12, pady=12, sticky="ew")

        ctk.CTkLabel(form, text="Password").grid(row=1, column=0, padx=12, pady=12, sticky="w")
        self.entry_password = ctk.CTkEntry(form, show="*", placeholder_text="••••••••", width=220)
        self.entry_password.grid(row=1, column=1, padx=12, pady=12, sticky="ew")

        ctk.CTkButton(
            self, text="Sign in", command=self.do_login, height=40
        ).grid(row=3, column=0, padx=30, pady=(20, 4), sticky="ew")

        ctk.CTkLabel(
            self, text="Default: admin / admin123  •  cashier / cashier123",
            text_color="gray50", font=ctk.CTkFont(size=11),
        ).grid(row=4, column=0, padx=20, pady=(10, 20), sticky="ew")

        self.entry_username.insert(0, "admin")
        self.entry_password.bind("<Return>", lambda _e: self.do_login())
        self.entry_username.focus_set()

    def do_login(self) -> None:
        username = self.entry_username.get().strip()
        password = self.entry_password.get()
        if not username or not password:
            messagebox.showerror("Login failed", "Please enter both username and password.")
            return
        user = self.db.authenticate(username, password)
        if user is None:
            messagebox.showerror("Login failed", "Invalid username or password.")
            return
        self.destroy()
        self.on_success(user)


class WarehouseApp(ctk.CTk):
    def __init__(self, db: Database, current_user: sqlite3.Row) -> None:
        super().__init__()
        self.db = db
        self.current_user = current_user
        self.is_admin = current_user["role"] == ROLE_ADMIN

        self.cart: List[Dict[str, Any]] = []
        self.selected_product_id: Optional[int] = None

        self.title(f"{APP_NAME} — {current_user['full_name']} ({current_user['role']})")
        self.geometry("1280x780")
        self.minsize(1100, 700)

        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("blue")

        self._build_layout()
        self._configure_treeview_style()
        self.show_dashboard()

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(99, weight=1)
        self.sidebar.grid_propagate(False)

        ctk.CTkLabel(
            self.sidebar, text=APP_NAME,
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, padx=12, pady=(18, 4), sticky="ew")
        ctk.CTkLabel(
            self.sidebar, text=f"👤 {self.current_user['full_name']}",
            text_color="gray40", font=ctk.CTkFont(size=11),
        ).grid(row=1, column=0, padx=12, pady=(0, 18), sticky="ew")

        self.nav_buttons: Dict[str, ctk.CTkButton] = {}
        nav_items = [
            ("dashboard", "📊 Dashboard", self.show_dashboard, True),
            ("inventory", "📦 Inventory", self.show_inventory, True),
            ("sale", "🛒 New Sale", self.show_sale, True),
            ("sales", "🧾 Sales History", self.show_sales, True),
            ("movements", "🔄 Stock Movements", self.show_movements, True),
            ("customers", "👥 Customers", self.show_customers, True),
            ("suppliers", "🚚 Suppliers", self.show_suppliers, True),
            ("reports", "📈 Reports", self.show_reports, self.is_admin),
            ("users", "👨‍💼 Users", self.show_users, self.is_admin),
            ("settings", "⚙ Settings", self.show_settings, self.is_admin),
            ("backup", "💾 Backup / Restore", self.show_backup, self.is_admin),
        ]
        for idx, (key, label, cmd, enabled) in enumerate(nav_items, start=2):
            if not enabled:
                continue
            btn = ctk.CTkButton(
                self.sidebar, text=label, anchor="w",
                fg_color="transparent", text_color=("gray10", "gray90"),
                hover_color=("gray70", "gray30"), height=36,
                command=cmd,
            )
            btn.grid(row=idx, column=0, padx=8, pady=2, sticky="ew")
            self.nav_buttons[key] = btn

        ctk.CTkButton(
            self.sidebar, text="⎋ Logout", anchor="w",
            fg_color="transparent", text_color="gray40",
            hover_color=("gray80", "gray25"), height=32,
            command=self.do_logout,
        ).grid(row=100, column=0, padx=8, pady=8, sticky="ew")
        ctk.CTkLabel(
            self.sidebar, text=f"v{APP_VERSION}", text_color="gray50",
            font=ctk.CTkFont(size=10),
        ).grid(row=101, column=0, padx=12, pady=(0, 10), sticky="ew")

        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray95", "gray15"))
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.pages: Dict[str, ctk.CTkFrame] = {}
        self._build_pages()
        self._set_active_nav("dashboard")

    def _build_pages(self) -> None:
        for key, builder in [
            ("dashboard", self._build_dashboard),
            ("inventory", self._build_inventory),
            ("sale", self._build_sale),
            ("sales", self._build_sales),
            ("movements", self._build_movements),
            ("customers", self._build_customers),
            ("suppliers", self._build_suppliers),
            ("reports", self._build_reports),
            ("users", self._build_users),
            ("settings", self._build_settings),
            ("backup", self._build_backup),
        ]:
            page = ctk.CTkFrame(self.content, corner_radius=0, fg_color="transparent")
            page.grid(row=0, column=0, sticky="nsew")
            page.grid_columnconfigure(0, weight=1)
            page.grid_rowconfigure(0, weight=1)
            builder(page)
            self.pages[key] = page

    def _set_active_nav(self, key: str) -> None:
        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.configure(fg_color=("gray70", "gray30"))
            else:
                btn.configure(fg_color="transparent")

    def show_page(self, key: str) -> None:
        page = self.pages.get(key)
        if page is not None:
            page.tkraise()
        self._set_active_nav(key)

    def show_dashboard(self) -> None:
        self.refresh_dashboard()
        self.show_page("dashboard")

    def show_inventory(self) -> None:
        self.refresh_inventory()
        self.show_page("inventory")

    def show_sale(self) -> None:
        self.cart.clear()
        self.refresh_cart()
        self.refresh_sale_search()
        self.show_page("sale")

    def show_sales(self) -> None:
        self.refresh_sales()
        self.show_page("sales")

    def show_movements(self) -> None:
        self.refresh_movements()
        self.show_page("movements")

    def show_customers(self) -> None:
        self.refresh_customers()
        self.show_page("customers")

    def show_suppliers(self) -> None:
        self.refresh_suppliers()
        self.show_page("suppliers")

    def show_reports(self) -> None:
        if not self.is_admin:
            messagebox.showwarning("Restricted", "Admins only.")
            return
        self.refresh_reports()
        self.show_page("reports")

    def show_users(self) -> None:
        if not self.is_admin:
            messagebox.showwarning("Restricted", "Admins only.")
            return
        self.refresh_users()
        self.show_page("users")

    def show_settings(self) -> None:
        if not self.is_admin:
            messagebox.showwarning("Restricted", "Admins only.")
            return
        self.refresh_settings()
        self.show_page("settings")

    def show_backup(self) -> None:
        if not self.is_admin:
            messagebox.showwarning("Restricted", "Admins only.")
            return
        self.show_page("backup")

    def _configure_treeview_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        base_font = ("Segoe UI", 11) if sys.platform.startswith("win") else ("DejaVu Sans", 11)
        style.configure("Treeview", rowheight=26, font=base_font)
        style.configure("Treeview.Heading", font=(base_font[0], 11, "bold"))
        self.tree.tag_configure(TAG_LOW_STOCK, background="#fff3cd", foreground="#7a5d00")
        self.tree.tag_configure(TAG_OUT_OF_STOCK, background="#ffd6d6", foreground="#7a1f1f")
        self.tree.tag_configure(TAG_OK_STOCK, background="#ffffff", foreground="#222222")

    def _page_header(self, parent: ctk.CTkFrame, title: str, subtitle: str = "") -> None:
        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 6))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            head, text=title, font=ctk.CTkFont(size=22, weight="bold")
        ).grid(row=0, column=0, sticky="w")
        if subtitle:
            ctk.CTkLabel(
                head, text=subtitle, text_color="gray50",
                font=ctk.CTkFont(size=12),
            ).grid(row=1, column=0, sticky="w", pady=(2, 0))

    def _build_dashboard(self, parent: ctk.CTkFrame) -> None:
        self._page_header(parent, "Dashboard", "Live overview of your warehouse")

        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        grid.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="cards")
        parent.grid_rowconfigure(1, weight=1)

        self.dash_cards: Dict[str, Tuple[ctk.CTkFrame, ctk.CTkLabel, ctk.CTkLabel]] = {}
        cards = [
            ("total_products", "📦 Products", "0"),
            ("stock_value", "💰 Stock Value", fmt_money(0)),
            ("low_stock", "⚠ Low Stock", "0"),
            ("out_of_stock", "❌ Out of Stock", "0"),
            ("today_sales", "🛒 Today's Sales", "0"),
            ("today_revenue", "💵 Today's Revenue", fmt_money(0)),
            ("month_sales", "📅 This Month's Sales", "0"),
            ("month_profit", "📈 This Month's Profit", fmt_money(0)),
        ]
        for idx, (key, label, value) in enumerate(cards):
            r, c = divmod(idx, 4)
            card = ctk.CTkFrame(grid, corner_radius=10)
            card.grid(row=r, column=c, padx=6, pady=6, sticky="nsew")
            card.grid_rowconfigure(0, weight=1)
            card.grid_rowconfigure(1, weight=1)
            lbl_label = ctk.CTkLabel(
                card, text=label, font=ctk.CTkFont(size=12), text_color="gray50"
            )
            lbl_label.grid(row=0, column=0, padx=14, pady=(14, 0), sticky="w")
            lbl_value = ctk.CTkLabel(
                card, text=value, font=ctk.CTkFont(size=20, weight="bold")
            )
            lbl_value.grid(row=1, column=0, padx=14, pady=(0, 14), sticky="w")
            self.dash_cards[key] = (card, lbl_label, lbl_value)

        bottom = ctk.CTkFrame(parent, fg_color="transparent")
        bottom.grid(row=2, column=0, sticky="nsew", padx=20, pady=10)
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            bottom, text="🏆 Top selling products (this month)",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=4, pady=(0, 6))
        ctk.CTkLabel(
            bottom, text="📊 Sales last 7 days",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=1, sticky="w", padx=4, pady=(0, 6))

        self.top_products_box = ctk.CTkTextbox(bottom, height=220, corner_radius=10)
        self.top_products_box.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        self.top_products_box.configure(state="disabled", font=ctk.CTkFont(size=12))

        self.weekly_chart_box = ctk.CTkTextbox(bottom, height=220, corner_radius=10)
        self.weekly_chart_box.grid(row=1, column=1, sticky="nsew", padx=4, pady=4)
        self.weekly_chart_box.configure(state="disabled", font=ctk.CTkFont(size=12, family="Courier"))

    def refresh_dashboard(self) -> None:
        s = self.db.dashboard_stats()
        self.dash_cards["total_products"][2].configure(text=f"{s['total_products']:,}")
        self.dash_cards["stock_value"][2].configure(text=fmt_money(s["total_stock_value"]))
        self.dash_cards["low_stock"][2].configure(text=f"{s['low_stock']:,}")
        self.dash_cards["out_of_stock"][2].configure(text=f"{s['out_of_stock']:,}")
        self.dash_cards["today_sales"][2].configure(text=f"{s['today_sales_count']:,}")
        self.dash_cards["today_revenue"][2].configure(text=fmt_money(s["today_sales_value"]))
        self.dash_cards["month_sales"][2].configure(text=f"{s['month_sales_count']:,}")
        self.dash_cards["month_profit"][2].configure(text=fmt_money(s["month_profit"]))

        self.top_products_box.configure(state="normal")
        self.top_products_box.delete("1.0", "end")
        if not s["top_products"]:
            self.top_products_box.insert("end", "  No sales recorded this month yet.\n")
        else:
            self.top_products_box.insert("end", f"  {'Product':<32}{'Qty':>8}{'Revenue':>16}\n")
            self.top_products_box.insert("end", "  " + "─" * 56 + "\n")
            for p in s["top_products"]:
                self.top_products_box.insert(
                    "end", f"  {p['product_name'][:30]:<32}{p['qty']:>8}{fmt_money(p['revenue']):>16}\n"
                )
        self.top_products_box.configure(state="disabled")

        self.weekly_chart_box.configure(state="normal")
        self.weekly_chart_box.delete("1.0", "end")
        rows = {r["d"]: r for r in self.db.sales_by_day(7)}
        max_total = max((r["total"] for r in rows.values()), default=0) or 1
        self.weekly_chart_box.insert("end", f"  {'Date':<12}{'Count':>7}{'Total':>16}   Chart\n")
        self.weekly_chart_box.insert("end", "  " + "─" * 60 + "\n")
        for i in range(6, -1, -1):
            d = (date.today() - timedelta(days=i)).isoformat()
            r = rows.get(d)
            cnt = r["cnt"] if r else 0
            total = r["total"] if r else 0.0
            bar_len = int((total / max_total) * 30)
            bar = "█" * bar_len
            self.weekly_chart_box.insert(
                "end", f"  {d:<12}{cnt:>7}{fmt_money(total):>16}   {bar}\n"
            )
        self.weekly_chart_box.configure(state="disabled")

    def _build_inventory(self, parent: ctk.CTkFrame) -> None:
        self._page_header(parent, "Inventory", "Manage your products and stock")

        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=20, pady=6)
        toolbar.grid_columnconfigure(6, weight=1)

        ctk.CTkLabel(toolbar, text="Category:").grid(row=0, column=0, padx=(0, 4), pady=4)
        self.inv_category = ctk.CTkComboBox(
            toolbar, values=["All"] + CATEGORIES, width=160, command=lambda _v: self.refresh_inventory()
        )
        self.inv_category.set("All")
        self.inv_category.grid(row=0, column=1, padx=4, pady=4)

        ctk.CTkLabel(toolbar, text="Search:").grid(row=0, column=2, padx=(12, 4), pady=4)
        self.inv_search = ctk.CTkEntry(toolbar, width=220, placeholder_text="name, SKU, brand, barcode…")
        self.inv_search.grid(row=0, column=3, padx=4, pady=4)
        self.inv_search.bind("<Return>", lambda _e: self.refresh_inventory())

        self.inv_low_only = ctk.CTkCheckBox(
            toolbar, text="Low stock only", command=self.refresh_inventory
        )
        self.inv_low_only.grid(row=0, column=4, padx=12, pady=4)

        self.inv_show_deleted = ctk.CTkCheckBox(
            toolbar, text="Show deleted", command=self.refresh_inventory
        )
        self.inv_show_deleted.grid(row=0, column=5, padx=4, pady=4)

        ctk.CTkButton(
            toolbar, text="🔄 Refresh", width=90, command=self.refresh_inventory
        ).grid(row=0, column=6, sticky="e", padx=4)
        ctk.CTkButton(
            toolbar, text="➕ New product", width=120, command=self.open_product_dialog
        ).grid(row=0, column=7, sticky="e", padx=4)

        tree_frame = ctk.CTkFrame(parent, corner_radius=10)
        tree_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(4, 10))
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        columns = ("id", "sku", "name", "category", "brand", "qty", "min", "purchase", "selling", "margin", "expiry")
        self.inv_tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", selectmode="browse"
        )
        widths = [
            ("id", "ID", 50, "center"),
            ("sku", "SKU", 90, "center"),
            ("name", "Product", 200, "w"),
            ("category", "Category", 130, "w"),
            ("brand", "Brand", 100, "w"),
            ("qty", "Stock", 70, "center"),
            ("min", "Min", 60, "center"),
            ("purchase", "Buy", 80, "e"),
            ("selling", "Sell", 80, "e"),
            ("margin", "Margin", 80, "e"),
            ("expiry", "Expiry", 90, "center"),
        ]
        for col, text, width, anchor in widths:
            self.inv_tree.heading(col, text=text)
            self.inv_tree.column(col, width=width, anchor=anchor, stretch=True)
        self.inv_tree.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.inv_tree.yview)
        self.inv_tree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="ns")

        self.inv_tree.bind("<<TreeviewSelect>>", self._on_inv_select)
        self.inv_tree.bind("<Double-1>", lambda _e: self.open_product_dialog(edit=True))
        self.tree = self.inv_tree

        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 12))
        ctk.CTkButton(actions, text="✏ Edit", width=90, command=lambda: self.open_product_dialog(edit=True)).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="📥 Restock", width=100, command=self.open_restock_dialog).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="🔧 Adjust stock", width=120, command=self.open_adjust_dialog).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="🏷 Barcode", width=100, command=self.open_barcode_dialog).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="🗑 Delete", width=90, fg_color="#b33939", hover_color="#8a2929", command=self.on_delete_product).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="♻ Restore", width=90, command=self.on_restore_product).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="📤 Export CSV", width=110, command=self.export_inventory_csv).pack(side="right", padx=4)

    def refresh_inventory(self) -> None:
        for item in self.inv_tree.get_children():
            self.inv_tree.delete(item)
        try:
            rows = self.db.list_products(
                category=self.inv_category.get(),
                search=self.inv_search.get().strip(),
                low_stock_only=self.inv_low_only.get(),
                include_deleted=self.inv_show_deleted.get(),
            )
        except sqlite3.Error as exc:
            messagebox.showerror("DB error", str(exc))
            return
        for r in rows:
            margin = r["selling_price"] - r["purchase_price"]
            if r["quantity"] == 0:
                tag = TAG_OUT_OF_STOCK
            elif r["quantity"] <= r["min_stock"]:
                tag = TAG_LOW_STOCK
            else:
                tag = TAG_OK_STOCK
            values = (
                r["id"], r["sku"], r["product_name"], r["category"], r["brand"] or "",
                fmt_qty(r["quantity"]), r["min_stock"],
                f"{r['purchase_price']:.2f}", f"{r['selling_price']:.2f}",
                f"{margin:.2f}", r["expiry_date"] or "",
            )
            self.inv_tree.insert("", "end", values=values, tags=(tag,))

    def _on_inv_select(self, _e=None) -> None:
        sel = self.inv_tree.selection()
        if not sel:
            self.selected_product_id = None
            return
        try:
            self.selected_product_id = int(self.inv_tree.item(sel[0], "values")[0])
        except (ValueError, IndexError):
            self.selected_product_id = None

    def open_product_dialog(self, edit: bool = False) -> None:
        if edit and self.selected_product_id is None:
            messagebox.showinfo("Select", "Please select a product first.")
            return
        if not edit and not self.is_admin:
            messagebox.showwarning("Restricted", "Only admins can add products.")
            return
        dlg = ProductDialog(
            self, self.db, self.is_admin,
            product_id=self.selected_product_id if edit else None,
        )
        if dlg.result:
            self.refresh_inventory()
            self.refresh_dashboard()

    def open_restock_dialog(self) -> None:
        if self.selected_product_id is None:
            messagebox.showinfo("Select", "Please select a product first.")
            return
        dlg = RestockDialog(self, self.db, self.selected_product_id)
        if dlg.result:
            self.refresh_inventory()
            self.refresh_dashboard()
            self.refresh_movements()

    def open_adjust_dialog(self) -> None:
        if self.selected_product_id is None:
            messagebox.showinfo("Select", "Please select a product first.")
            return
        dlg = AdjustDialog(self, self.db, self.selected_product_id)
        if dlg.result:
            self.refresh_inventory()
            self.refresh_dashboard()
            self.refresh_movements()

    def open_barcode_dialog(self) -> None:
        if self.selected_product_id is None:
            messagebox.showinfo("Select", "Please select a product first.")
            return
        BarcodeDialog(self, self.db, self.selected_product_id)

    def on_delete_product(self) -> None:
        if self.selected_product_id is None:
            messagebox.showinfo("Select", "Please select a product first.")
            return
        if not self.is_admin:
            messagebox.showwarning("Restricted", "Admins only.")
            return
        row = self.db.get_product(self.selected_product_id)
        if row is None:
            return
        if not messagebox.askyesno(
            "Confirm", f"Delete product '{row['product_name']}'?\nUse 'Restore' to bring it back."
        ):
            return
        try:
            self.db.soft_delete_product(self.selected_product_id)
        except sqlite3.Error as exc:
            messagebox.showerror("DB error", str(exc))
            return
        self.refresh_inventory()
        self.refresh_dashboard()

    def on_restore_product(self) -> None:
        if self.selected_product_id is None:
            messagebox.showinfo("Select", "Please select a product first.")
            return
        if not self.is_admin:
            messagebox.showwarning("Restricted", "Admins only.")
            return
        self.db.restore_product(self.selected_product_id)
        self.refresh_inventory()
        self.refresh_dashboard()

    def export_inventory_csv(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile=f"inventory_{date.today().isoformat()}.csv",
        )
        if not path:
            return
        rows = self.db.list_products(include_deleted=self.inv_show_deleted.get())
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["ID", "SKU", "Barcode", "Product", "Category", "Brand", "Unit",
                        "Quantity", "Min stock", "Purchase price", "Selling price",
                        "Expiry", "Supplier", "Deleted"])
            for r in rows:
                w.writerow([
                    r["id"], r["sku"], r["barcode"] or "", r["product_name"],
                    r["category"], r["brand"] or "", r["unit"],
                    r["quantity"], r["min_stock"],
                    r["purchase_price"], r["selling_price"],
                    r["expiry_date"] or "", r["supplier_name"] or "",
                    "yes" if r["is_deleted"] else "no",
                ])
        messagebox.showinfo("Exported", f"Inventory exported to:\n{path}")

    def _build_sale(self, parent: ctk.CTkFrame) -> None:
        self._page_header(parent, "New Sale", "Build a cart and checkout")

        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        left = ctk.CTkFrame(parent, corner_radius=10)
        left.grid(row=1, column=0, sticky="nsew", padx=(20, 6), pady=6)
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text="Find product", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 4)
        )
        search_row = ctk.CTkFrame(left, fg_color="transparent")
        search_row.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        search_row.grid_columnconfigure(0, weight=1)
        self.sale_search = ctk.CTkEntry(search_row, placeholder_text="Search by name, SKU, or scan barcode…")
        self.sale_search.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.sale_search.bind("<KeyRelease>", lambda _e: self.refresh_sale_search())
        self.sale_search.bind("<Return>", lambda _e: self.add_barcode_to_cart())
        ctk.CTkButton(search_row, text="➕ Add", width=80, command=self.add_selected_to_cart).grid(
            row=0, column=1, padx=4
        )

        results_frame = ctk.CTkFrame(left, fg_color="transparent")
        results_frame.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 8))
        results_frame.grid_rowconfigure(0, weight=1)
        results_frame.grid_columnconfigure(0, weight=1)

        cols = ("id", "name", "category", "price", "stock")
        self.sale_results = ttk.Treeview(
            results_frame, columns=cols, show="headings", selectmode="browse", height=10
        )
        for col, text, w, a in [
            ("id", "ID", 50, "center"),
            ("name", "Product", 220, "w"),
            ("category", "Category", 120, "w"),
            ("price", "Sell price", 90, "e"),
            ("stock", "Stock", 70, "center"),
        ]:
            self.sale_results.heading(col, text=text)
            self.sale_results.column(col, width=w, anchor=a, stretch=True)
        self.sale_results.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(results_frame, orient="vertical", command=self.sale_results.yview)
        self.sale_results.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="ns")
        self.sale_results.bind("<Double-1>", lambda _e: self.add_selected_to_cart())
        self.sale_results.tag_configure(TAG_OUT_OF_STOCK, background="#ffd6d6", foreground="#7a1f1f")
        self.sale_results.tag_configure(TAG_OK_STOCK, background="#ffffff", foreground="#222222")

        right = ctk.CTkFrame(parent, corner_radius=10)
        right.grid(row=1, column=1, sticky="nsew", padx=(6, 20), pady=6)
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(right, text="Cart", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 4)
        )

        cart_frame = ctk.CTkFrame(right, fg_color="transparent")
        cart_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=4)
        cart_frame.grid_rowconfigure(0, weight=1)
        cart_frame.grid_columnconfigure(0, weight=1)

        ccols = ("name", "qty", "price", "total")
        self.cart_tree = ttk.Treeview(
            cart_frame, columns=ccols, show="headings", selectmode="browse", height=10
        )
        for col, text, w, a in [
            ("name", "Product", 240, "w"),
            ("qty", "Qty", 70, "center"),
            ("price", "Unit", 90, "e"),
            ("total", "Total", 100, "e"),
        ]:
            self.cart_tree.heading(col, text=text)
            self.cart_tree.column(col, width=w, anchor=a, stretch=True)
        self.cart_tree.grid(row=0, column=0, sticky="nsew")
        cvsb = ttk.Scrollbar(cart_frame, orient="vertical", command=self.cart_tree.yview)
        self.cart_tree.configure(yscrollcommand=cvsb.set)
        cvsb.grid(row=0, column=1, sticky="ns")
        self.cart_tree.bind("<Double-1>", lambda _e: self.edit_cart_qty())

        cart_actions = ctk.CTkFrame(right, fg_color="transparent")
        cart_actions.grid(row=2, column=0, sticky="ew", padx=12, pady=4)
        ctk.CTkButton(cart_actions, text="✏ Edit qty", width=90, command=self.edit_cart_qty).pack(side="left", padx=2)
        ctk.CTkButton(cart_actions, text="🗑 Remove", width=90, command=self.remove_from_cart).pack(side="left", padx=2)
        ctk.CTkButton(cart_actions, text="🧹 Clear cart", width=100, fg_color="gray", hover_color="dimgray", command=self.clear_cart).pack(side="right", padx=2)

        totals = ctk.CTkFrame(right, corner_radius=8)
        totals.grid(row=3, column=0, sticky="ew", padx=12, pady=8)
        totals.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(totals, text="Subtotal:").grid(row=0, column=0, sticky="w", padx=10, pady=4)
        self.lbl_subtotal = ctk.CTkLabel(totals, text=fmt_money(0), font=ctk.CTkFont(weight="bold"))
        self.lbl_subtotal.grid(row=0, column=1, sticky="e", padx=10, pady=4)

        ctk.CTkLabel(totals, text="Discount:").grid(row=1, column=0, sticky="w", padx=10, pady=4)
        self.entry_discount = ctk.CTkEntry(totals, width=120, placeholder_text="0.00")
        self.entry_discount.grid(row=1, column=1, sticky="e", padx=10, pady=4)
        self.entry_discount.bind("<KeyRelease>", lambda _e: self.update_totals())

        ctk.CTkLabel(totals, text="Tax:").grid(row=2, column=0, sticky="w", padx=10, pady=4)
        self.entry_tax = ctk.CTkEntry(totals, width=120, placeholder_text="0.00")
        self.entry_tax.grid(row=2, column=1, sticky="e", padx=10, pady=4)
        self.entry_tax.bind("<KeyRelease>", lambda _e: self.update_totals())

        ctk.CTkLabel(totals, text="TOTAL:", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=3, column=0, sticky="w", padx=10, pady=8
        )
        self.lbl_total = ctk.CTkLabel(
            totals, text=fmt_money(0), font=ctk.CTkFont(size=18, weight="bold"), text_color="#1d6f42"
        )
        self.lbl_total.grid(row=3, column=1, sticky="e", padx=10, pady=8)

        checkout = ctk.CTkFrame(parent, corner_radius=10)
        checkout.grid(row=2, column=0, columnspan=2, sticky="ew", padx=20, pady=(6, 12))
        checkout.grid_columnconfigure(6, weight=1)

        ctk.CTkLabel(checkout, text="Customer:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.sale_customer = ctk.CTkComboBox(checkout, values=["Walk-in"], width=200, command=lambda _v: None)
        self.sale_customer.set("Walk-in")
        self.sale_customer.grid(row=0, column=1, padx=4, pady=10)
        ctk.CTkButton(checkout, text="➕ New", width=60, command=self.quick_add_customer).grid(row=0, column=2, padx=4, pady=10)

        ctk.CTkLabel(checkout, text="Payment:").grid(row=0, column=3, padx=(20, 4), pady=10, sticky="w")
        self.sale_payment = ctk.CTkComboBox(checkout, values=["cash", "card", "credit", "transfer"], width=110)
        self.sale_payment.set("cash")
        self.sale_payment.grid(row=0, column=4, padx=4, pady=10)

        ctk.CTkLabel(checkout, text="Paid:").grid(row=0, column=5, padx=(20, 4), pady=10, sticky="w")
        self.entry_paid = ctk.CTkEntry(checkout, width=100, placeholder_text="0.00")
        self.entry_paid.grid(row=0, column=6, sticky="w", padx=4, pady=10)
        self.entry_paid.bind("<KeyRelease>", lambda _e: self.update_totals())

        ctk.CTkButton(
            checkout, text="✅ Checkout", width=140, height=40,
            fg_color="#1d6f42", hover_color="#155232",
            command=self.do_checkout,
        ).grid(row=0, column=7, padx=10, pady=10)

    def refresh_sale_search(self) -> None:
        for item in self.sale_results.get_children():
            self.sale_results.delete(item)
        try:
            rows = self.db.list_products(search=self.sale_search.get().strip())
        except sqlite3.Error as exc:
            messagebox.showerror("DB error", str(exc))
            return
        for r in rows:
            tag = TAG_OUT_OF_STOCK if r["quantity"] == 0 else TAG_OK_STOCK
            self.sale_results.insert(
                "", "end",
                values=(r["id"], r["product_name"], r["category"],
                        f"{r['selling_price']:.2f}", fmt_qty(r["quantity"])),
                tags=(tag,),
            )

    def add_barcode_to_cart(self) -> None:
        code = self.sale_search.get().strip()
        if not code:
            return
        product = self.db.find_product_by_barcode(code)
        if product is None:
            return
        self._add_product_to_cart(product, qty=1)
        self.sale_search.delete(0, "end")
        self.refresh_sale_search()

    def add_selected_to_cart(self) -> None:
        sel = self.sale_results.selection()
        if not sel:
            return
        try:
            pid = int(self.sale_results.item(sel[0], "values")[0])
        except (ValueError, IndexError):
            return
        product = self.db.get_product(pid)
        if product is None:
            return
        self._add_product_to_cart(product, qty=1)

    def _add_product_to_cart(self, product: sqlite3.Row, qty: int = 1) -> None:
        if product["quantity"] <= 0:
            messagebox.showwarning("Out of stock", f"'{product['product_name']}' is out of stock.")
            return
        for item in self.cart:
            if item["product_id"] == product["id"]:
                if item["quantity"] + qty > product["quantity"]:
                    messagebox.showwarning(
                        "Insufficient stock",
                        f"Only {product['quantity']} units available.",
                    )
                    return
                item["quantity"] += qty
                self.refresh_cart()
                return
        if qty > product["quantity"]:
            messagebox.showwarning("Insufficient stock", f"Only {product['quantity']} units available.")
            return
        self.cart.append({
            "product_id": product["id"],
            "product_name": product["product_name"],
            "quantity": qty,
            "unit_price": product["selling_price"],
            "purchase_price": product["purchase_price"],
            "max_qty": product["quantity"],
        })
        self.refresh_cart()

    def remove_from_cart(self) -> None:
        sel = self.cart_tree.selection()
        if not sel:
            return
        idx = self.cart_tree.index(sel[0])
        if 0 <= idx < len(self.cart):
            del self.cart[idx]
            self.refresh_cart()

    def edit_cart_qty(self) -> None:
        sel = self.cart_tree.selection()
        if not sel:
            return
        idx = self.cart_tree.index(sel[0])
        if not (0 <= idx < len(self.cart)):
            return
        item = self.cart[idx]
        new_qty = simpledialog.askinteger(
            "Edit quantity", f"Quantity for '{item['product_name']}':",
            initialvalue=item["quantity"], minvalue=1, maxvalue=item["max_qty"],
        )
        if new_qty is None:
            return
        item["quantity"] = new_qty
        self.refresh_cart()

    def clear_cart(self) -> None:
        self.cart.clear()
        self.refresh_cart()

    def refresh_cart(self) -> None:
        for item in self.cart_tree.get_children():
            self.cart_tree.delete(item)
        for item in self.cart:
            self.cart_tree.insert(
                "", "end",
                values=(
                    item["product_name"],
                    fmt_qty(item["quantity"]),
                    f"{item['unit_price']:.2f}",
                    f"{item['quantity'] * item['unit_price']:.2f}",
                ),
            )
        self.update_totals()

    def _parse_money(self, value: str) -> float:
        s = value.strip().replace(",", ".")
        return float(s) if s else 0.0

    def update_totals(self) -> None:
        subtotal = sum(i["quantity"] * i["unit_price"] for i in self.cart)
        try:
            discount = self._parse_money(self.entry_discount.get())
        except ValueError:
            discount = 0.0
        try:
            tax = self._parse_money(self.entry_tax.get())
        except ValueError:
            tax = 0.0
        total = max(0.0, subtotal - discount + tax)
        self.lbl_subtotal.configure(text=fmt_money(subtotal))
        self.lbl_total.configure(text=fmt_money(total))

    def quick_add_customer(self) -> None:
        dlg = CustomerDialog(self, self.db, is_admin=self.is_admin)
        if dlg.result:
            customers = self.db.list_customers()
            self.sale_customer.configure(values=["Walk-in"] + [c["name"] for c in customers])
            self.sale_customer.set(dlg.result["name"])

    def _current_customer_id(self) -> Optional[int]:
        name = self.sale_customer.get().strip()
        if not name or name == "Walk-in":
            return None
        for c in self.db.list_customers():
            if c["name"] == name:
                return c["id"]
        return None

    def do_checkout(self) -> None:
        if not self.cart:
            messagebox.showinfo("Empty cart", "Add at least one product.")
            return
        try:
            discount = self._parse_money(self.entry_discount.get())
        except ValueError:
            messagebox.showerror("Invalid", "Discount must be a number.")
            return
        try:
            tax = self._parse_money(self.entry_tax.get())
        except ValueError:
            messagebox.showerror("Invalid", "Tax must be a number.")
            return
        try:
            amount_paid = self._parse_money(self.entry_paid.get())
        except ValueError:
            messagebox.showerror("Invalid", "Amount paid must be a number.")
            return

        try:
            sale_id, invoice = self.db.create_sale(
                user_id=self.current_user["id"],
                items=self.cart,
                customer_id=self._current_customer_id(),
                discount=discount,
                tax=tax,
                payment_method=self.sale_payment.get(),
                amount_paid=amount_paid,
                notes="",
            )
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror("Checkout failed", str(exc))
            return

        InvoiceDialog(self, self.db, sale_id, invoice)
        self.cart.clear()
        self.entry_discount.delete(0, "end")
        self.entry_tax.delete(0, "end")
        self.entry_paid.delete(0, "end")
        self.refresh_cart()
        self.refresh_sale_search()
        self.refresh_dashboard()
        self.refresh_sales()

    def _build_sales(self, parent: ctk.CTkFrame) -> None:
        self._page_header(parent, "Sales History", "All past invoices")

        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=20, pady=6)
        toolbar.grid_columnconfigure(8, weight=1)

        ctk.CTkLabel(toolbar, text="From:").grid(row=0, column=0, padx=4, pady=4)
        self.sales_from = ctk.CTkEntry(toolbar, width=110, placeholder_text="YYYY-MM-DD")
        self.sales_from.grid(row=0, column=1, padx=4, pady=4)
        ctk.CTkLabel(toolbar, text="To:").grid(row=0, column=2, padx=4, pady=4)
        self.sales_to = ctk.CTkEntry(toolbar, width=110, placeholder_text="YYYY-MM-DD")
        self.sales_to.grid(row=0, column=3, padx=4, pady=4)
        ctk.CTkButton(toolbar, text="Today", width=60, command=lambda: self._set_sales_range("today")).grid(row=0, column=4, padx=4)
        ctk.CTkButton(toolbar, text="7 days", width=60, command=lambda: self._set_sales_range("week")).grid(row=0, column=5, padx=4)
        ctk.CTkButton(toolbar, text="Month", width=60, command=lambda: self._set_sales_range("month")).grid(row=0, column=6, padx=4)
        ctk.CTkButton(toolbar, text="🔄 Apply", width=80, command=self.refresh_sales).grid(row=0, column=7, padx=4)
        ctk.CTkButton(toolbar, text="📤 CSV", width=80, command=self.export_sales_csv).grid(row=0, column=9, sticky="e", padx=4)

        tree_frame = ctk.CTkFrame(parent, corner_radius=10)
        tree_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(4, 10))
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        cols = ("id", "invoice", "date", "customer", "cashier", "items", "total", "payment")
        self.sales_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        for col, text, w, a in [
            ("id", "ID", 50, "center"),
            ("invoice", "Invoice", 160, "w"),
            ("date", "Date", 140, "w"),
            ("customer", "Customer", 160, "w"),
            ("cashier", "Cashier", 130, "w"),
            ("items", "Items", 60, "center"),
            ("total", "Total", 100, "e"),
            ("payment", "Payment", 80, "center"),
        ]:
            self.sales_tree.heading(col, text=text)
            self.sales_tree.column(col, width=w, anchor=a, stretch=True)
        self.sales_tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.sales_tree.yview)
        self.sales_tree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="ns")
        self.sales_tree.bind("<Double-1>", lambda _e: self.view_selected_sale())

        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 12))
        ctk.CTkButton(actions, text="👁 View / Print", width=120, command=self.view_selected_sale).pack(side="left", padx=4)

    def _set_sales_range(self, kind: str) -> None:
        today = date.today()
        if kind == "today":
            self.sales_from.delete(0, "end"); self.sales_from.insert(0, today.isoformat())
            self.sales_to.delete(0, "end"); self.sales_to.insert(0, today.isoformat())
        elif kind == "week":
            start = today - timedelta(days=6)
            self.sales_from.delete(0, "end"); self.sales_from.insert(0, start.isoformat())
            self.sales_to.delete(0, "end"); self.sales_to.insert(0, today.isoformat())
        elif kind == "month":
            start = today.replace(day=1)
            self.sales_from.delete(0, "end"); self.sales_from.insert(0, start.isoformat())
            self.sales_to.delete(0, "end"); self.sales_to.insert(0, today.isoformat())

    def refresh_sales(self) -> None:
        for item in self.sales_tree.get_children():
            self.sales_tree.delete(item)
        df = self.sales_from.get().strip() or None
        dt = self.sales_to.get().strip() or None
        try:
            rows = self.db.list_sales(date_from=df, date_to=dt, limit=500)
        except sqlite3.Error as exc:
            messagebox.showerror("DB error", str(exc))
            return
        for r in rows:
            items = self.db.get_sale_items(r["id"])
            self.sales_tree.insert(
                "", "end",
                values=(
                    r["id"], r["invoice_number"], fmt_date(r["created_at"]),
                    r["customer_name"] or "Walk-in", r["user_name"] or "",
                    len(items), f"{r['total']:.2f}", r["payment_method"],
                ),
            )

    def view_selected_sale(self) -> None:
        sel = self.sales_tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Please select a sale.")
            return
        try:
            sale_id = int(self.sales_tree.item(sel[0], "values")[0])
        except (ValueError, IndexError):
            return
        sale = self.db.get_sale(sale_id)
        if sale is None:
            return
        InvoiceDialog(self, self.db, sale_id, sale["invoice_number"], read_only=True)

    def export_sales_csv(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile=f"sales_{date.today().isoformat()}.csv",
        )
        if not path:
            return
        df = self.sales_from.get().strip() or None
        dt = self.sales_to.get().strip() or None
        rows = self.db.list_sales(date_from=df, date_to=dt, limit=10000)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["ID", "Invoice", "Date", "Customer", "Cashier", "Subtotal", "Discount", "Tax", "Total", "Payment"])
            for r in rows:
                w.writerow([
                    r["id"], r["invoice_number"], r["created_at"],
                    r["customer_name"] or "Walk-in", r["user_name"] or "",
                    r["subtotal"], r["discount"], r["tax"], r["total"], r["payment_method"],
                ])
        messagebox.showinfo("Exported", f"Sales exported to:\n{path}")

    def _build_movements(self, parent: ctk.CTkFrame) -> None:
        self._page_header(parent, "Stock Movements", "Complete audit trail of every stock change")

        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=20, pady=6)
        toolbar.grid_columnconfigure(6, weight=1)

        ctk.CTkLabel(toolbar, text="Product:").grid(row=0, column=0, padx=4, pady=4)
        self.mov_product = ctk.CTkComboBox(
            toolbar, values=["All"], width=220, command=lambda _v: self.refresh_movements()
        )
        self.mov_product.set("All")
        self.mov_product.grid(row=0, column=1, padx=4, pady=4)

        ctk.CTkLabel(toolbar, text="From:").grid(row=0, column=2, padx=4, pady=4)
        self.mov_from = ctk.CTkEntry(toolbar, width=110, placeholder_text="YYYY-MM-DD")
        self.mov_from.grid(row=0, column=3, padx=4, pady=4)
        ctk.CTkLabel(toolbar, text="To:").grid(row=0, column=4, padx=4, pady=4)
        self.mov_to = ctk.CTkEntry(toolbar, width=110, placeholder_text="YYYY-MM-DD")
        self.mov_to.grid(row=0, column=5, padx=4, pady=4)
        ctk.CTkButton(toolbar, text="🔄 Apply", width=80, command=self.refresh_movements).grid(row=0, column=7, sticky="e", padx=4)
        ctk.CTkButton(toolbar, text="📤 CSV", width=80, command=self.export_movements_csv).grid(row=0, column=8, sticky="e", padx=4)

        tree_frame = ctk.CTkFrame(parent, corner_radius=10)
        tree_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(4, 12))
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        cols = ("date", "type", "product", "delta", "before", "after", "value", "user", "ref")
        self.mov_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        for col, text, w, a in [
            ("date", "Date", 140, "w"),
            ("type", "Type", 90, "center"),
            ("product", "Product", 200, "w"),
            ("delta", "Δ Qty", 70, "center"),
            ("before", "Before", 70, "center"),
            ("after", "After", 70, "center"),
            ("value", "Value", 90, "e"),
            ("user", "User", 120, "w"),
            ("ref", "Reference", 180, "w"),
        ]:
            self.mov_tree.heading(col, text=text)
            self.mov_tree.column(col, width=w, anchor=a, stretch=True)
        self.mov_tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.mov_tree.yview)
        self.mov_tree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="ns")
        self.mov_tree.tag_configure("in", background="#e6f7ec", foreground="#155232")
        self.mov_tree.tag_configure("out", background="#fdecec", foreground="#7a1f1f")
        self.mov_tree.tag_configure("adj", background="#fff8e1", foreground="#7a5d00")

    def refresh_movements(self) -> None:
        products = self.db.list_products(include_deleted=True)
        self.mov_product.configure(values=["All"] + [f"{p['sku']} — {p['product_name']}" for p in products])
        sel = self.mov_product.get()
        product_id: Optional[int] = None
        if sel and sel != "All":
            for p in products:
                if f"{p['sku']} — {p['product_name']}" == sel:
                    product_id = p["id"]
                    break

        for item in self.mov_tree.get_children():
            self.mov_tree.delete(item)
        try:
            rows = self.db.list_movements(
                product_id=product_id,
                date_from=self.mov_from.get().strip() or None,
                date_to=self.mov_to.get().strip() or None,
                limit=1000,
            )
        except sqlite3.Error as exc:
            messagebox.showerror("DB error", str(exc))
            return
        for r in rows:
            if r["movement_type"] in ("restock", "return"):
                tag = "in"
            elif r["movement_type"] == "sale":
                tag = "out"
            else:
                tag = "adj"
            delta = r["quantity_delta"]
            self.mov_tree.insert(
                "", "end",
                values=(
                    fmt_date(r["created_at"]), r["movement_type"].upper(),
                    r["product_name"] or f"#{r['product_id']}",
                    f"{delta:+d}", r["quantity_before"], r["quantity_after"],
                    f"{r['total_value']:.2f}", r["user_name"] or "", r["reference"] or "",
                ),
                tags=(tag,),
            )

    def export_movements_csv(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile=f"movements_{date.today().isoformat()}.csv",
        )
        if not path:
            return
        rows = self.db.list_movements(limit=10000)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["Date", "Type", "Product", "Delta", "Before", "After", "Value", "User", "Reference", "Notes"])
            for r in rows:
                w.writerow([
                    r["created_at"], r["movement_type"], r["product_name"] or "",
                    r["quantity_delta"], r["quantity_before"], r["quantity_after"],
                    r["total_value"], r["user_name"] or "", r["reference"] or "", r["notes"] or "",
                ])
        messagebox.showinfo("Exported", f"Movements exported to:\n{path}")

    def _build_customers(self, parent: ctk.CTkFrame) -> None:
        self._page_header(parent, "Customers", "Your customer database")

        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=20, pady=6)
        toolbar.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(toolbar, text="Search:").grid(row=0, column=0, padx=4)
        self.cust_search = ctk.CTkEntry(toolbar, placeholder_text="name or phone…", width=240)
        self.cust_search.grid(row=0, column=1, sticky="w", padx=4)
        self.cust_search.bind("<KeyRelease>", lambda _e: self.refresh_customers())
        ctk.CTkButton(toolbar, text="🔄 Refresh", width=90, command=self.refresh_customers).grid(row=0, column=2, padx=4)
        ctk.CTkButton(toolbar, text="➕ New customer", width=120, command=self.open_customer_dialog).grid(row=0, column=3, padx=4)

        tree_frame = ctk.CTkFrame(parent, corner_radius=10)
        tree_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(4, 10))
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        cols = ("id", "name", "phone", "email", "address", "created")
        self.cust_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        for col, text, w, a in [
            ("id", "ID", 50, "center"),
            ("name", "Name", 200, "w"),
            ("phone", "Phone", 130, "w"),
            ("email", "Email", 180, "w"),
            ("address", "Address", 220, "w"),
            ("created", "Created", 130, "w"),
        ]:
            self.cust_tree.heading(col, text=text)
            self.cust_tree.column(col, width=w, anchor=a, stretch=True)
        self.cust_tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.cust_tree.yview)
        self.cust_tree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="ns")
        self.cust_tree.bind("<Double-1>", lambda _e: self.open_customer_dialog(edit=True))

        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 12))
        ctk.CTkButton(actions, text="✏ Edit", width=90, command=lambda: self.open_customer_dialog(edit=True)).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="🗑 Delete", width=90, fg_color="#b33939", hover_color="#8a2929", command=self.delete_customer).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="📤 CSV", width=90, command=self.export_customers_csv).pack(side="right", padx=4)

    def refresh_customers(self) -> None:
        for item in self.cust_tree.get_children():
            self.cust_tree.delete(item)
        q = self.cust_search.get().strip()
        rows = self.db.search_customers(q) if q else self.db.list_customers()
        for r in rows:
            self.cust_tree.insert(
                "", "end",
                values=(r["id"], r["name"], r["phone"] or "", r["email"] or "",
                        r["address"] or "", fmt_date(r["created_at"])),
            )

    def open_customer_dialog(self, edit: bool = False) -> None:
        cid = None
        if edit:
            sel = self.cust_tree.selection()
            if not sel:
                messagebox.showinfo("Select", "Please select a customer."); return
            try:
                cid = int(self.cust_tree.item(sel[0], "values")[0])
            except (ValueError, IndexError):
                return
        dlg = CustomerDialog(self, self.db, is_admin=self.is_admin, customer_id=cid)
        if dlg.result:
            self.refresh_customers()

    def delete_customer(self) -> None:
        sel = self.cust_tree.selection()
        if not sel:
            return
        try:
            cid = int(self.cust_tree.item(sel[0], "values")[0])
        except (ValueError, IndexError):
            return
        if not messagebox.askyesno("Confirm", "Delete this customer?"):
            return
        try:
            self.db.delete_customer(cid)
        except sqlite3.Error as exc:
            messagebox.showerror("DB error", str(exc)); return
        self.refresh_customers()

    def export_customers_csv(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        rows = self.db.list_customers()
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["ID", "Name", "Phone", "Email", "Address", "Notes", "Created"])
            for r in rows:
                w.writerow([r["id"], r["name"], r["phone"] or "", r["email"] or "",
                            r["address"] or "", r["notes"] or "", r["created_at"]])
        messagebox.showinfo("Exported", f"Customers exported to:\n{path}")

    def _build_suppliers(self, parent: ctk.CTkFrame) -> None:
        self._page_header(parent, "Suppliers", "Your supplier database")

        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=20, pady=6)
        ctk.CTkButton(toolbar, text="🔄 Refresh", width=90, command=self.refresh_suppliers).grid(row=0, column=0, padx=4)
        ctk.CTkButton(toolbar, text="➕ New supplier", width=120, command=self.open_supplier_dialog).grid(row=0, column=1, padx=4)

        tree_frame = ctk.CTkFrame(parent, corner_radius=10)
        tree_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(4, 10))
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        cols = ("id", "name", "phone", "email", "address")
        self.sup_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        for col, text, w, a in [
            ("id", "ID", 50, "center"),
            ("name", "Name", 220, "w"),
            ("phone", "Phone", 140, "w"),
            ("email", "Email", 200, "w"),
            ("address", "Address", 260, "w"),
        ]:
            self.sup_tree.heading(col, text=text)
            self.sup_tree.column(col, width=w, anchor=a, stretch=True)
        self.sup_tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.sup_tree.yview)
        self.sup_tree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="ns")
        self.sup_tree.bind("<Double-1>", lambda _e: self.open_supplier_dialog(edit=True))

        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 12))
        ctk.CTkButton(actions, text="✏ Edit", width=90, command=lambda: self.open_supplier_dialog(edit=True)).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="🗑 Delete", width=90, fg_color="#b33939", hover_color="#8a2929", command=self.delete_supplier).pack(side="left", padx=4)

    def refresh_suppliers(self) -> None:
        for item in self.sup_tree.get_children():
            self.sup_tree.delete(item)
        for r in self.db.list_suppliers():
            self.sup_tree.insert("", "end", values=(r["id"], r["name"], r["phone"] or "", r["email"] or "", r["address"] or ""))

    def open_supplier_dialog(self, edit: bool = False) -> None:
        sid = None
        if edit:
            sel = self.sup_tree.selection()
            if not sel:
                messagebox.showinfo("Select", "Please select a supplier."); return
            try:
                sid = int(self.sup_tree.item(sel[0], "values")[0])
            except (ValueError, IndexError):
                return
        dlg = SupplierDialog(self, self.db, supplier_id=sid)
        if dlg.result:
            self.refresh_suppliers()

    def delete_supplier(self) -> None:
        sel = self.sup_tree.selection()
        if not sel:
            return
        try:
            sid = int(self.sup_tree.item(sel[0], "values")[0])
        except (ValueError, IndexError):
            return
        if not messagebox.askyesno("Confirm", "Delete this supplier?"):
            return
        try:
            self.db.delete_supplier(sid)
        except sqlite3.Error as exc:
            messagebox.showerror("DB error", str(exc)); return
        self.refresh_suppliers()

    def _build_reports(self, parent: ctk.CTkFrame) -> None:
        self._page_header(parent, "Reports", "Sales, profit and inventory analytics")

        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=20, pady=6)
        ctk.CTkLabel(toolbar, text="Period:").grid(row=0, column=0, padx=4)
        self.report_period = ctk.CTkComboBox(
            toolbar, values=["Today", "Last 7 days", "This month", "Last 30 days", "This year"], width=160
        )
        self.report_period.set("This month")
        self.report_period.grid(row=0, column=1, padx=4)
        ctk.CTkButton(toolbar, text="🔄 Generate", width=100, command=self.refresh_reports).grid(row=0, column=2, padx=4)

        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.grid(row=2, column=0, sticky="nsew", padx=20, pady=10)
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        grid.grid_rowconfigure(0, weight=1)
        grid.grid_rowconfigure(1, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        self.report_summary = ctk.CTkTextbox(grid, font=ctk.CTkFont(size=12, family="Courier"))
        self.report_summary.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.report_summary.configure(state="disabled")

        self.report_top = ctk.CTkTextbox(grid, font=ctk.CTkFont(size=12))
        self.report_top.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)
        self.report_top.configure(state="disabled")

        self.report_by_cat = ctk.CTkTextbox(grid, font=ctk.CTkFont(size=12, family="Courier"))
        self.report_by_cat.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        self.report_by_cat.configure(state="disabled")

        self.report_inventory = ctk.CTkTextbox(grid, font=ctk.CTkFont(size=12, family="Courier"))
        self.report_inventory.grid(row=1, column=1, sticky="nsew", padx=4, pady=4)
        self.report_inventory.configure(state="disabled")

    def _report_dates(self) -> Tuple[str, str]:
        period = self.report_period.get()
        today = date.today()
        if period == "Today":
            return today.isoformat(), today.isoformat()
        if period == "Last 7 days":
            return (today - timedelta(days=6)).isoformat(), today.isoformat()
        if period == "This month":
            return today.replace(day=1).isoformat(), today.isoformat()
        if period == "Last 30 days":
            return (today - timedelta(days=29)).isoformat(), today.isoformat()
        return today.replace(month=1, day=1).isoformat(), today.isoformat()

    def refresh_reports(self) -> None:
        df, dt = self._report_dates()
        sales = self.db.list_sales(date_from=df, date_to=dt, limit=100000)
        total_revenue = sum(s["total"] for s in sales)
        total_discount = sum(s["discount"] for s in sales)
        total_tax = sum(s["tax"] for s in sales)

        profit = 0.0
        for s in sales:
            for it in self.db.get_sale_items(s["id"]):
                profit += (it["unit_price"] - it["purchase_price"]) * it["quantity"]

        avg_ticket = (total_revenue / len(sales)) if sales else 0.0
        payment_breakdown: Dict[str, float] = {}
        for s in sales:
            payment_breakdown[s["payment_method"]] = payment_breakdown.get(s["payment_method"], 0.0) + s["total"]

        self.report_summary.configure(state="normal")
        self.report_summary.delete("1.0", "end")
        self.report_summary.insert("end", f"  SALES REPORT — {df} → {dt}\n")
        self.report_summary.insert("end", "  " + "═" * 50 + "\n\n")
        self.report_summary.insert("end", f"  Invoices issued:    {len(sales):>8}\n")
        self.report_summary.insert("end", f"  Total revenue:      {fmt_money(total_revenue):>14}\n")
        self.report_summary.insert("end", f"  Total discounts:    {fmt_money(total_discount):>14}\n")
        self.report_summary.insert("end", f"  Total tax:          {fmt_money(total_tax):>14}\n")
        self.report_summary.insert("end", f"  Gross profit:       {fmt_money(profit):>14}\n")
        self.report_summary.insert("end", f"  Average ticket:     {fmt_money(avg_ticket):>14}\n\n")
        self.report_summary.insert("end", "  Payment breakdown:\n")
        for method, amount in sorted(payment_breakdown.items(), key=lambda x: -x[1]):
            self.report_summary.insert("end", f"    {method:<14} {fmt_money(amount):>14}\n")
        self.report_summary.configure(state="disabled")

        product_sales: Dict[str, Dict[str, float]] = {}
        for s in sales:
            for it in self.db.get_sale_items(s["id"]):
                key = it["product_name"]
                if key not in product_sales:
                    product_sales[key] = {"qty": 0, "revenue": 0.0, "profit": 0.0}
                product_sales[key]["qty"] += it["quantity"]
                product_sales[key]["revenue"] += it["line_total"]
                product_sales[key]["profit"] += (it["unit_price"] - it["purchase_price"]) * it["quantity"]

        self.report_top.configure(state="normal")
        self.report_top.delete("1.0", "end")
        self.report_top.insert("end", f"  TOP SELLING PRODUCTS\n")
        self.report_top.insert("end", "  " + "═" * 60 + "\n\n")
        self.report_top.insert("end", f"  {'Product':<28}{'Qty':>7}{'Revenue':>13}{'Profit':>13}\n")
        self.report_top.insert("end", "  " + "─" * 60 + "\n")
        for name, data in sorted(product_sales.items(), key=lambda x: -x[1]["revenue"])[:15]:
            self.report_top.insert(
                "end",
                f"  {name[:27]:<28}{int(data['qty']):>7}{fmt_money(data['revenue']):>13}{fmt_money(data['profit']):>13}\n",
            )
        self.report_top.configure(state="disabled")

        cat_sales: Dict[str, Dict[str, float]] = {}
        for s in sales:
            for it in self.db.get_sale_items(s["id"]):
                prod = self.db.get_product(it["product_id"])
                cat = prod["category"] if prod else "Unknown"
                if cat not in cat_sales:
                    cat_sales[cat] = {"qty": 0, "revenue": 0.0}
                cat_sales[cat]["qty"] += it["quantity"]
                cat_sales[cat]["revenue"] += it["line_total"]

        self.report_by_cat.configure(state="normal")
        self.report_by_cat.delete("1.0", "end")
        self.report_by_cat.insert("end", f"  SALES BY CATEGORY\n")
        self.report_by_cat.insert("end", "  " + "═" * 50 + "\n\n")
        self.report_by_cat.insert("end", f"  {'Category':<28}{'Qty':>8}{'Revenue':>14}\n")
        self.report_by_cat.insert("end", "  " + "─" * 50 + "\n")
        for cat, data in sorted(cat_sales.items(), key=lambda x: -x[1]["revenue"]):
            self.report_by_cat.insert(
                "end",
                f"  {cat[:27]:<28}{int(data['qty']):>8}{fmt_money(data['revenue']):>14}\n",
            )
        self.report_by_cat.configure(state="disabled")

        products = self.db.list_products()
        total_value = sum(p["quantity"] * p["purchase_price"] for p in products)
        low_stock = [p for p in products if p["quantity"] <= p["min_stock"]]
        self.report_inventory.configure(state="normal")
        self.report_inventory.delete("1.0", "end")
        self.report_inventory.insert("end", f"  INVENTORY SNAPSHOT\n")
        self.report_inventory.insert("end", "  " + "═" * 50 + "\n\n")
        self.report_inventory.insert("end", f"  Active products:    {len(products):>8}\n")
        self.report_inventory.insert("end", f"  Stock value (cost): {fmt_money(total_value):>14}\n")
        self.report_inventory.insert("end", f"  Low/out of stock:   {len(low_stock):>8}\n\n")
        if low_stock:
            self.report_inventory.insert("end", "  ITEMS NEEDING RESTOCK\n")
            self.report_inventory.insert("end", "  " + "─" * 50 + "\n")
            for p in low_stock[:15]:
                self.report_inventory.insert(
                    "end",
                    f"  {p['product_name'][:32]:<32} {p['quantity']:>4} / min {p['min_stock']}\n",
                )
        self.report_inventory.configure(state="disabled")

    def _build_users(self, parent: ctk.CTkFrame) -> None:
        self._page_header(parent, "Users", "Manage who can access the system")

        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=20, pady=6)
        ctk.CTkButton(toolbar, text="🔄 Refresh", width=90, command=self.refresh_users).grid(row=0, column=0, padx=4)
        ctk.CTkButton(toolbar, text="➕ New user", width=100, command=self.open_user_dialog).grid(row=0, column=1, padx=4)

        tree_frame = ctk.CTkFrame(parent, corner_radius=10)
        tree_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(4, 10))
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        cols = ("id", "username", "name", "role", "active", "created")
        self.users_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        for col, text, w, a in [
            ("id", "ID", 50, "center"),
            ("username", "Username", 140, "w"),
            ("name", "Full name", 200, "w"),
            ("role", "Role", 100, "center"),
            ("active", "Active", 70, "center"),
            ("created", "Created", 140, "w"),
        ]:
            self.users_tree.heading(col, text=text)
            self.users_tree.column(col, width=w, anchor=a, stretch=True)
        self.users_tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.users_tree.yview)
        self.users_tree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="ns")
        self.users_tree.bind("<Double-1>", lambda _e: self.open_user_dialog(edit=True))

        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 12))
        ctk.CTkButton(actions, text="✏ Edit", width=90, command=lambda: self.open_user_dialog(edit=True)).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="🔑 Reset password", width=140, command=self.reset_user_password).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="🗑 Delete", width=90, fg_color="#b33939", hover_color="#8a2929", command=self.delete_user).pack(side="left", padx=4)

    def refresh_users(self) -> None:
        for item in self.users_tree.get_children():
            self.users_tree.delete(item)
        for r in self.db.list_users():
            self.users_tree.insert(
                "", "end",
                values=(r["id"], r["username"], r["full_name"], r["role"],
                        "yes" if r["is_active"] else "no", fmt_date(r["created_at"])),
            )

    def open_user_dialog(self, edit: bool = False) -> None:
        uid = None
        if edit:
            sel = self.users_tree.selection()
            if not sel:
                messagebox.showinfo("Select", "Please select a user."); return
            try:
                uid = int(self.users_tree.item(sel[0], "values")[0])
            except (ValueError, IndexError):
                return
        dlg = UserDialog(self, self.db, user_id=uid)
        if dlg.result:
            self.refresh_users()

    def reset_user_password(self) -> None:
        sel = self.users_tree.selection()
        if not sel:
            return
        try:
            uid = int(self.users_tree.item(sel[0], "values")[0])
        except (ValueError, IndexError):
            return
        new_pw = simpledialog.askstring("Reset password", "New password (min 4 chars):", show="*")
        if not new_pw or len(new_pw) < 4:
            messagebox.showerror("Invalid", "Password must be at least 4 characters."); return
        self.db.reset_user_password(uid, new_pw)
        messagebox.showinfo("Done", "Password has been reset.")

    def delete_user(self) -> None:
        sel = self.users_tree.selection()
        if not sel:
            return
        try:
            uid = int(self.users_tree.item(sel[0], "values")[0])
        except (ValueError, IndexError):
            return
        if uid == self.current_user["id"]:
            messagebox.showwarning("Nope", "You cannot delete your own account."); return
        if not messagebox.askyesno("Confirm", "Delete this user?"):
            return
        try:
            self.db.delete_user(uid)
        except sqlite3.Error as exc:
            messagebox.showerror("DB error", str(exc)); return
        self.refresh_users()

    def _build_settings(self, parent: ctk.CTkFrame) -> None:
        self._page_header(parent, "Settings", "Store information and preferences")

        form = ctk.CTkFrame(parent, corner_radius=10)
        form.grid(row=1, column=0, sticky="ew", padx=20, pady=10)
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="Store name:").grid(row=0, column=0, sticky="w", padx=12, pady=8)
        self.set_store_name = ctk.CTkEntry(form)
        self.set_store_name.grid(row=0, column=1, sticky="ew", padx=12, pady=8)

        ctk.CTkLabel(form, text="Store phone:").grid(row=1, column=0, sticky="w", padx=12, pady=8)
        self.set_store_phone = ctk.CTkEntry(form)
        self.set_store_phone.grid(row=1, column=1, sticky="ew", padx=12, pady=8)

        ctk.CTkLabel(form, text="Store address:").grid(row=2, column=0, sticky="w", padx=12, pady=8)
        self.set_store_address = ctk.CTkEntry(form)
        self.set_store_address.grid(row=2, column=1, sticky="ew", padx=12, pady=8)

        ctk.CTkLabel(form, text="Default tax rate (%):").grid(row=3, column=0, sticky="w", padx=12, pady=8)
        self.set_tax_rate = ctk.CTkEntry(form)
        self.set_tax_rate.grid(row=3, column=1, sticky="ew", padx=12, pady=8)

        ctk.CTkButton(form, text="💾 Save settings", command=self.save_settings).grid(
            row=4, column=1, sticky="e", padx=12, pady=12
        )

        info = ctk.CTkFrame(parent, corner_radius=10)
        info.grid(row=2, column=0, sticky="ew", padx=20, pady=10)
        ctk.CTkLabel(
            info, text="All settings are stored locally in the database file.\n"
                       "Use Backup & Restore to copy the database safely.",
            text_color="gray50", justify="left",
        ).grid(row=0, column=0, padx=14, pady=14, sticky="w")

        self.refresh_settings()

    def refresh_settings(self) -> None:
        self.set_store_name.delete(0, "end")
        self.set_store_name.insert(0, self.db.get_setting("store_name", ""))
        self.set_store_phone.delete(0, "end")
        self.set_store_phone.insert(0, self.db.get_setting("store_phone", ""))
        self.set_store_address.delete(0, "end")
        self.set_store_address.insert(0, self.db.get_setting("store_address", ""))
        self.set_tax_rate.delete(0, "end")
        self.set_tax_rate.insert(0, self.db.get_setting("tax_rate", "0"))

    def save_settings(self) -> None:
        self.db.set_setting("store_name", self.set_store_name.get().strip())
        self.db.set_setting("store_phone", self.set_store_phone.get().strip())
        self.db.set_setting("store_address", self.set_store_address.get().strip())
        self.db.set_setting("tax_rate", self.set_tax_rate.get().strip())
        messagebox.showinfo("Saved", "Settings saved.")

    def _build_backup(self, parent: ctk.CTkFrame) -> None:
        self._page_header(parent, "Backup & Restore", "Protect your data")

        box = ctk.CTkFrame(parent, corner_radius=10)
        box.grid(row=1, column=0, sticky="ew", padx=20, pady=10)
        box.grid_columnconfigure(0, weight=1)
        box.grid_columnconfigure(1, weight=1)

        backup_card = ctk.CTkFrame(box, corner_radius=10)
        backup_card.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        ctk.CTkLabel(backup_card, text="💾 Backup", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, padx=14, pady=(14, 6), sticky="w"
        )
        ctk.CTkLabel(backup_card, text="Save a copy of the database to a safe place.\nRecommended daily.",
                     text_color="gray50", justify="left").grid(row=1, column=0, padx=14, pady=4, sticky="w")
        ctk.CTkButton(backup_card, text="Create backup now", command=self.do_backup).grid(
            row=2, column=0, padx=14, pady=14, sticky="ew"
        )

        restore_card = ctk.CTkFrame(box, corner_radius=10)
        restore_card.grid(row=0, column=1, padx=8, pady=8, sticky="nsew")
        ctk.CTkLabel(restore_card, text="📥 Restore", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, padx=14, pady=(14, 6), sticky="w"
        )
        ctk.CTkLabel(
            restore_card, text="Restore from a backup file.\n⚠ This will replace the current database.",
            text_color="gray50", justify="left",
        ).grid(row=1, column=0, padx=14, pady=4, sticky="w")
        ctk.CTkButton(
            restore_card, text="Restore from file", fg_color="#b33939", hover_color="#8a2929",
            command=self.do_restore,
        ).grid(row=2, column=0, padx=14, pady=14, sticky="ew")

        info = ctk.CTkFrame(parent, corner_radius=10)
        info.grid(row=2, column=0, sticky="ew", padx=20, pady=10)
        ctk.CTkLabel(
            info, text=f"Database location:\n{self.db.db_path}",
            font=ctk.CTkFont(size=12, family="Courier"),
        ).grid(row=0, column=0, padx=14, pady=14, sticky="w")

    def do_backup(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".db", filetypes=[("SQLite database", "*.db")],
            initialfile=f"warehouse_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
        )
        if not path:
            return
        try:
            self.db.backup(path)
        except OSError as exc:
            messagebox.showerror("Backup failed", str(exc))
            return
        messagebox.showinfo("Backup complete", f"Saved to:\n{path}")

    def do_restore(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("SQLite database", "*.db"), ("All files", "*.*")])
        if not path:
            return
        if not messagebox.askyesno(
            "Confirm restore",
            "This will REPLACE the current database with the backup.\n"
            "Any data added after the backup will be lost.\n\nContinue?",
        ):
            return
        try:
            self.db.restore(path)
        except OSError as exc:
            messagebox.showerror("Restore failed", str(exc))
            return
        messagebox.showinfo("Restored", "Database restored. The app will now reload.")
        self.do_logout(reload=True)

    def do_logout(self, reload: bool = False) -> None:
        self.db.close()
        self.destroy()
        if reload:
            os.execl(sys.executable, sys.executable, *sys.argv)

    def on_closing(self) -> None:
        try:
            self.db.close()
        finally:
            self.destroy()


class ProductDialog(ctk.CTkToplevel):
    def __init__(self, parent, db: Database, is_admin: bool, product_id: Optional[int] = None) -> None:
        super().__init__(parent)
        self.db = db
        self.is_admin = is_admin
        self.product_id = product_id
        self.result = False
        self.existing: Optional[sqlite3.Row] = None

        self.title("Edit product" if product_id else "New product")
        self.geometry("560x720")
        self.transient(parent)
        self.grab_set()

        frm = ctk.CTkFrame(self, corner_radius=10)
        frm.pack(fill="both", expand=True, padx=14, pady=14)
        frm.grid_columnconfigure(1, weight=1)

        row = 0
        ctk.CTkLabel(frm, text="Product name *:").grid(row=row, column=0, sticky="w", padx=10, pady=6)
        self.f_name = ctk.CTkEntry(frm, width=320); self.f_name.grid(row=row, column=1, sticky="ew", padx=10, pady=6)
        row += 1

        ctk.CTkLabel(frm, text="SKU *:").grid(row=row, column=0, sticky="w", padx=10, pady=6)
        sku_frame = ctk.CTkFrame(frm, fg_color="transparent"); sku_frame.grid(row=row, column=1, sticky="ew", padx=10, pady=6)
        self.f_sku = ctk.CTkEntry(sku_frame, placeholder_text="auto")
        self.f_sku.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(sku_frame, text="🎲", width=40, command=self._gen_sku).pack(side="left", padx=4)
        row += 1

        ctk.CTkLabel(frm, text="Barcode:").grid(row=row, column=0, sticky="w", padx=10, pady=6)
        bc_frame = ctk.CTkFrame(frm, fg_color="transparent"); bc_frame.grid(row=row, column=1, sticky="ew", padx=10, pady=6)
        self.f_barcode = ctk.CTkEntry(bc_frame); self.f_barcode.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(bc_frame, text="🎲", width=40, command=self._gen_barcode).pack(side="left", padx=4)
        row += 1

        ctk.CTkLabel(frm, text="Category *:").grid(row=row, column=0, sticky="w", padx=10, pady=6)
        self.f_category = ctk.CTkComboBox(frm, values=CATEGORIES, width=320)
        self.f_category.set(CATEGORIES[0])
        self.f_category.grid(row=row, column=1, sticky="ew", padx=10, pady=6)
        row += 1

        ctk.CTkLabel(frm, text="Brand:").grid(row=row, column=0, sticky="w", padx=10, pady=6)
        self.f_brand = ctk.CTkEntry(frm); self.f_brand.grid(row=row, column=1, sticky="ew", padx=10, pady=6)
        row += 1

        ctk.CTkLabel(frm, text="Unit:").grid(row=row, column=0, sticky="w", padx=10, pady=6)
        self.f_unit = ctk.CTkComboBox(frm, values=["piece", "bottle", "box", "bag", "kg", "liter", "pack"])
        self.f_unit.set("piece")
        self.f_unit.grid(row=row, column=1, sticky="ew", padx=10, pady=6)
        row += 1

        ctk.CTkLabel(frm, text="Quantity *:").grid(row=row, column=0, sticky="w", padx=10, pady=6)
        self.f_qty = ctk.CTkEntry(frm); self.f_qty.grid(row=row, column=1, sticky="ew", padx=10, pady=6)
        row += 1

        ctk.CTkLabel(frm, text="Min stock alert:").grid(row=row, column=0, sticky="w", padx=10, pady=6)
        self.f_min = ctk.CTkEntry(frm); self.f_min.insert(0, "10")
        self.f_min.grid(row=row, column=1, sticky="ew", padx=10, pady=6)
        row += 1

        ctk.CTkLabel(frm, text="Purchase price *:").grid(row=row, column=0, sticky="w", padx=10, pady=6)
        self.f_purchase = ctk.CTkEntry(frm); self.f_purchase.grid(row=row, column=1, sticky="ew", padx=10, pady=6)
        row += 1

        ctk.CTkLabel(frm, text="Selling price *:").grid(row=row, column=0, sticky="w", padx=10, pady=6)
        self.f_selling = ctk.CTkEntry(frm); self.f_selling.grid(row=row, column=1, sticky="ew", padx=10, pady=6)
        row += 1

        ctk.CTkLabel(frm, text="Expiry date:").grid(row=row, column=0, sticky="w", padx=10, pady=6)
        self.f_expiry = ctk.CTkEntry(frm, placeholder_text="YYYY-MM-DD (optional)")
        self.f_expiry.grid(row=row, column=1, sticky="ew", padx=10, pady=6)
        row += 1

        ctk.CTkLabel(frm, text="Supplier:").grid(row=row, column=0, sticky="w", padx=10, pady=6)
        self.f_supplier = ctk.CTkComboBox(frm, values=["—"], width=320)
        suppliers = self.db.list_suppliers()
        self.suppliers_map = {"—": None}
        for s in suppliers:
            self.suppliers_map[s["name"]] = s["id"]
        self.f_supplier.configure(values=list(self.suppliers_map.keys()))
        self.f_supplier.set("—")
        self.f_supplier.grid(row=row, column=1, sticky="ew", padx=10, pady=6)
        row += 1

        ctk.CTkLabel(frm, text="Notes:").grid(row=row, column=0, sticky="nw", padx=10, pady=6)
        self.f_notes = ctk.CTkTextbox(frm, height=70)
        self.f_notes.grid(row=row, column=1, sticky="ew", padx=10, pady=6)
        row += 1

        btns = ctk.CTkFrame(frm, fg_color="transparent")
        btns.grid(row=row, column=0, columnspan=2, sticky="ew", padx=10, pady=14)
        btns.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(btns, text="Cancel", fg_color="gray", hover_color="dimgray", command=self.destroy).grid(
            row=0, column=0, sticky="ew", padx=4
        )
        ctk.CTkButton(btns, text="Save", command=self._save).grid(
            row=0, column=1, sticky="ew", padx=4
        )

        if product_id is not None:
            self.existing = self.db.get_product(product_id)
            if self.existing:
                self.f_name.insert(0, self.existing["product_name"])
                self.f_sku.insert(0, self.existing["sku"])
                if self.existing["barcode"]:
                    self.f_barcode.insert(0, self.existing["barcode"])
                self.f_category.set(self.existing["category"])
                if self.existing["brand"]:
                    self.f_brand.insert(0, self.existing["brand"])
                self.f_unit.set(self.existing["unit"])
                self.f_qty.insert(0, str(self.existing["quantity"]))
                self.f_min.delete(0, "end"); self.f_min.insert(0, str(self.existing["min_stock"]))
                self.f_purchase.insert(0, str(self.existing["purchase_price"]))
                self.f_selling.insert(0, str(self.existing["selling_price"]))
                if self.existing["expiry_date"]:
                    self.f_expiry.insert(0, self.existing["expiry_date"])
                if self.existing["supplier_id"]:
                    for name, sid in self.suppliers_map.items():
                        if sid == self.existing["supplier_id"]:
                            self.f_supplier.set(name)
                            break
                if self.existing["notes"]:
                    self.f_notes.insert("1.0", self.existing["notes"])
                if not is_admin:
                    for w in (self.f_name, self.f_sku, self.f_purchase, self.f_selling, self.f_min):
                        w.configure(state="disabled")
        else:
            self.f_qty.insert(0, "0")
            self.f_purchase.insert(0, "0.00")
            self.f_selling.insert(0, "0.00")
            self._gen_sku()
            self._gen_barcode()

    def _gen_sku(self) -> None:
        self.f_sku.delete(0, "end")
        self.f_sku.insert(0, self.db.generate_sku())

    def _gen_barcode(self) -> None:
        self.f_barcode.delete(0, "end")
        self.f_barcode.insert(0, str(secrets.randbelow(10**12)).zfill(12))

    def _save(self) -> None:
        try:
            data = {
                "sku": self.f_sku.get().strip() or self.db.generate_sku(),
                "barcode": self.f_barcode.get().strip(),
                "product_name": self.f_name.get().strip(),
                "category": self.f_category.get(),
                "brand": self.f_brand.get().strip(),
                "unit": self.f_unit.get(),
                "quantity": parse_int(self.f_qty.get(), "Quantity", allow_zero=True),
                "min_stock": parse_int(self.f_min.get(), "Min stock", allow_zero=True),
                "purchase_price": parse_float(self.f_purchase.get(), "Purchase price"),
                "selling_price": parse_float(self.f_selling.get(), "Selling price"),
                "expiry_date": parse_date(self.f_expiry.get()),
                "supplier_id": self.suppliers_map.get(self.f_supplier.get()),
                "notes": self.f_notes.get("1.0", "end").strip(),
            }
            if not data["product_name"]:
                raise ValueError("Product name is required.")
            if data["selling_price"] < data["purchase_price"]:
                if not messagebox.askyesno(
                    "Heads up",
                    "Selling price is lower than purchase price. Save anyway?",
                ):
                    return
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc))
            return

        try:
            if self.existing is not None:
                new_qty = data["quantity"]
                old_qty = self.existing["quantity"]
                self.db.update_product(self.existing["id"], data)
                if new_qty != old_qty:
                    self.db._record_movement(
                        product_id=self.existing["id"],
                        movement_type="adjustment",
                        delta=new_qty - old_qty,
                        unit_price=data["purchase_price"],
                        reference="Manual edit",
                        user_id=None,
                        notes=f"Quantity changed from {old_qty} to {new_qty}",
                    )
                    self.db.conn.commit()
            else:
                self.db.add_product(data, user_id=None)
        except sqlite3.IntegrityError as exc:
            messagebox.showerror("Duplicate", f"A product with that name, SKU, or barcode already exists.\n\n{exc}")
            return
        except sqlite3.Error as exc:
            messagebox.showerror("DB error", str(exc)); return

        self.result = True
        self.destroy()


class RestockDialog(ctk.CTkToplevel):
    def __init__(self, parent, db: Database, product_id: int) -> None:
        super().__init__(parent)
        self.db = db
        self.product_id = product_id
        self.result = False

        product = db.get_product(product_id)
        if product is None:
            self.destroy(); return

        self.title("Restock")
        self.geometry("420x300")
        self.transient(parent); self.grab_set()

        frm = ctk.CTkFrame(self, corner_radius=10)
        frm.pack(fill="both", expand=True, padx=14, pady=14)
        frm.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frm, text=product["product_name"], font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, columnspan=2, padx=10, pady=(8, 4), sticky="w"
        )
        ctk.CTkLabel(frm, text=f"Current stock: {fmt_qty(product['quantity'])}",
                     text_color="gray50").grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="w")

        ctk.CTkLabel(frm, text="Add quantity:").grid(row=2, column=0, padx=10, pady=8, sticky="w")
        self.f_qty = ctk.CTkEntry(frm, width=200); self.f_qty.grid(row=2, column=1, padx=10, pady=8, sticky="ew")

        ctk.CTkLabel(frm, text="Unit cost:").grid(row=3, column=0, padx=10, pady=8, sticky="w")
        self.f_cost = ctk.CTkEntry(frm, width=200)
        self.f_cost.insert(0, str(product["purchase_price"]))
        self.f_cost.grid(row=3, column=1, padx=10, pady=8, sticky="ew")

        ctk.CTkLabel(frm, text="Notes:").grid(row=4, column=0, padx=10, pady=8, sticky="w")
        self.f_notes = ctk.CTkEntry(frm); self.f_notes.grid(row=4, column=1, padx=10, pady=8, sticky="ew")

        btns = ctk.CTkFrame(frm, fg_color="transparent")
        btns.grid(row=5, column=0, columnspan=2, sticky="ew", padx=10, pady=14)
        btns.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(btns, text="Cancel", fg_color="gray", hover_color="dimgray", command=self.destroy).grid(
            row=0, column=0, sticky="ew", padx=4
        )
        ctk.CTkButton(btns, text="✅ Restock", command=self._save).grid(row=0, column=1, sticky="ew", padx=4)

    def _save(self) -> None:
        try:
            qty = parse_int(self.f_qty.get(), "Quantity", allow_zero=False)
            cost = parse_float(self.f_cost.get(), "Unit cost")
        except ValueError as exc:
            messagebox.showerror("Invalid", str(exc)); return
        notes = self.f_notes.get().strip()
        try:
            self.db.restock_product(self.product_id, qty, cost, 0, notes)
        except sqlite3.Error as exc:
            messagebox.showerror("DB error", str(exc)); return
        self.result = True
        self.destroy()


class AdjustDialog(ctk.CTkToplevel):
    def __init__(self, parent, db: Database, product_id: int) -> None:
        super().__init__(parent)
        self.db = db
        self.product_id = product_id
        self.result = False

        product = db.get_product(product_id)
        if product is None:
            self.destroy(); return

        self.title("Adjust stock")
        self.geometry("420x260")
        self.transient(parent); self.grab_set()

        frm = ctk.CTkFrame(self, corner_radius=10)
        frm.pack(fill="both", expand=True, padx=14, pady=14)
        frm.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frm, text=product["product_name"], font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, columnspan=2, padx=10, pady=(8, 4), sticky="w"
        )
        ctk.CTkLabel(frm, text=f"Current stock: {fmt_qty(product['quantity'])}",
                     text_color="gray50").grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="w")

        ctk.CTkLabel(frm, text="New quantity:").grid(row=2, column=0, padx=10, pady=8, sticky="w")
        self.f_new = ctk.CTkEntry(frm)
        self.f_new.insert(0, str(product["quantity"]))
        self.f_new.grid(row=2, column=1, padx=10, pady=8, sticky="ew")

        ctk.CTkLabel(frm, text="Reason:").grid(row=3, column=0, padx=10, pady=8, sticky="w")
        self.f_reason = ctk.CTkEntry(frm, placeholder_text="e.g. damaged, recount…")
        self.f_reason.grid(row=3, column=1, padx=10, pady=8, sticky="ew")

        btns = ctk.CTkFrame(frm, fg_color="transparent")
        btns.grid(row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=14)
        btns.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(btns, text="Cancel", fg_color="gray", hover_color="dimgray", command=self.destroy).grid(
            row=0, column=0, sticky="ew", padx=4
        )
        ctk.CTkButton(btns, text="💾 Save", command=self._save).grid(row=0, column=1, sticky="ew", padx=4)

    def _save(self) -> None:
        try:
            new_qty = parse_int(self.f_new.get(), "New quantity", allow_zero=True)
        except ValueError as exc:
            messagebox.showerror("Invalid", str(exc)); return
        reason = self.f_reason.get().strip()
        try:
            self.db.adjust_stock(self.product_id, new_qty, 0, reason)
        except sqlite3.Error as exc:
            messagebox.showerror("DB error", str(exc)); return
        self.result = True
        self.destroy()


class BarcodeDialog(ctk.CTkToplevel):
    def __init__(self, parent, db: Database, product_id: int) -> None:
        super().__init__(parent)
        self.db = db
        self.product_id = product_id
        product = db.get_product(product_id)
        if product is None:
            self.destroy(); return

        self.title(f"Barcode — {product['product_name']}")
        self.geometry("420x520")
        self.transient(parent); self.grab_set()

        frm = ctk.CTkFrame(self, corner_radius=10)
        frm.pack(fill="both", expand=True, padx=14, pady=14)
        frm.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frm, text=product["product_name"], font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, padx=10, pady=(8, 4)
        )
        ctk.CTkLabel(frm, text=f"SKU: {product['sku']}").grid(row=1, column=0, padx=10, pady=2)

        ctk.CTkLabel(frm, text="Barcode value:").grid(row=2, column=0, padx=10, pady=(14, 4), sticky="w")
        self.f_barcode = ctk.CTkEntry(frm)
        self.f_barcode.insert(0, product["barcode"] or "")
        self.f_barcode.grid(row=3, column=0, padx=10, pady=4, sticky="ew")

        ctk.CTkButton(frm, text="💾 Save barcode", command=self._save).grid(row=4, column=0, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(frm, text="Generated barcode:").grid(row=5, column=0, padx=10, pady=(10, 4), sticky="w")
        self.image_label = ctk.CTkLabel(frm, text="(generate to see preview)")
        self.image_label.grid(row=6, column=0, padx=10, pady=4)

        ctk.CTkButton(frm, text="🔄 Generate preview", command=self._generate).grid(
            row=7, column=0, padx=10, pady=8, sticky="ew"
        )
        ctk.CTkButton(frm, text="📥 Save as PNG", command=self._save_png).grid(
            row=8, column=0, padx=10, pady=4, sticky="ew"
        )

        self._preview_image = None

    def _save(self) -> None:
        bc = self.f_barcode.get().strip()
        try:
            self.db.conn.execute(
                "UPDATE products SET barcode = ? WHERE id = ?;", (bc or None, self.product_id)
            )
            self.db.conn.commit()
        except sqlite3.IntegrityError:
            messagebox.showerror("Duplicate", "That barcode is already used by another product.")
            return
        except sqlite3.Error as exc:
            messagebox.showerror("DB error", str(exc)); return
        messagebox.showinfo("Saved", "Barcode saved.")
        self.destroy()

    def _generate(self) -> None:
        try:
            import barcode
            from barcode.writer import ImageWriter
            from PIL import Image, ImageTk
        except ImportError:
            messagebox.showerror(
                "Missing dependency",
                "Install barcode and pillow:\npip install python-barcode Pillow",
            )
            return
        code = self.f_barcode.get().strip()
        if not code or not code.isdigit() or len(code) < 8:
            messagebox.showerror("Invalid", "Barcode must be a numeric string of at least 8 digits.")
            return
        try:
            ean = barcode.get("ean13", code.zfill(12)[:12], writer=ImageWriter())
            buf = io.BytesIO()
            ean.write(buf, options={"module_height": 8.0, "font_size": 8, "quiet_zone": 2.0})
            buf.seek(0)
            img = Image.open(buf)
            self._preview_image = img.copy()
            img.thumbnail((360, 200))
            photo = ImageTk.PhotoImage(img)
            self.image_label.configure(image=photo, text="")
            self.image_label.image = photo
        except Exception as exc:
            messagebox.showerror("Barcode error", str(exc))

    def _save_png(self) -> None:
        if self._preview_image is None:
            messagebox.showinfo("No preview", "Generate the barcode first."); return
        path = filedialog.asksaveasfilename(
            defaultextension=".png", filetypes=[("PNG", "*.png")],
            initialfile=f"barcode_{self.f_barcode.get().strip()}.png",
        )
        if not path:
            return
        try:
            self._preview_image.save(path)
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc)); return
        messagebox.showinfo("Saved", f"Barcode saved to:\n{path}")


class CustomerDialog(ctk.CTkToplevel):
    def __init__(self, parent, db: Database, is_admin: bool = True, customer_id: Optional[int] = None) -> None:
        super().__init__(parent)
        self.db = db
        self.result: Optional[Dict[str, Any]] = None
        self.is_admin = is_admin

        self.title("Edit customer" if customer_id else "New customer")
        self.geometry("460x420")
        self.transient(parent); self.grab_set()

        frm = ctk.CTkFrame(self, corner_radius=10)
        frm.pack(fill="both", expand=True, padx=14, pady=14)
        frm.grid_columnconfigure(1, weight=1)

        row = 0
        ctk.CTkLabel(frm, text="Name *:").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        self.f_name = ctk.CTkEntry(frm); self.f_name.grid(row=row, column=1, sticky="ew", padx=10, pady=8)
        row += 1

        ctk.CTkLabel(frm, text="Phone:").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        self.f_phone = ctk.CTkEntry(frm); self.f_phone.grid(row=row, column=1, sticky="ew", padx=10, pady=8)
        row += 1

        ctk.CTkLabel(frm, text="Email:").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        self.f_email = ctk.CTkEntry(frm); self.f_email.grid(row=row, column=1, sticky="ew", padx=10, pady=8)
        row += 1

        ctk.CTkLabel(frm, text="Address:").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        self.f_address = ctk.CTkEntry(frm); self.f_address.grid(row=row, column=1, sticky="ew", padx=10, pady=8)
        row += 1

        ctk.CTkLabel(frm, text="Notes:").grid(row=row, column=0, sticky="nw", padx=10, pady=8)
        self.f_notes = ctk.CTkTextbox(frm, height=80)
        self.f_notes.grid(row=row, column=1, sticky="ew", padx=10, pady=8)
        row += 1

        btns = ctk.CTkFrame(frm, fg_color="transparent")
        btns.grid(row=row, column=0, columnspan=2, sticky="ew", padx=10, pady=14)
        btns.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(btns, text="Cancel", fg_color="gray", hover_color="dimgray", command=self.destroy).grid(
            row=0, column=0, sticky="ew", padx=4
        )
        ctk.CTkButton(btns, text="Save", command=self._save).grid(row=0, column=1, sticky="ew", padx=4)

        if customer_id is not None:
            for c in self.db.list_customers():
                if c["id"] == customer_id:
                    self.f_name.insert(0, c["name"])
                    if c["phone"]: self.f_phone.insert(0, c["phone"])
                    if c["email"]: self.f_email.insert(0, c["email"])
                    if c["address"]: self.f_address.insert(0, c["address"])
                    if c["notes"]: self.f_notes.insert("1.0", c["notes"])
                    break

    def _save(self) -> None:
        name = self.f_name.get().strip()
        if not name:
            messagebox.showerror("Invalid", "Name is required."); return
        data = {
            "name": name,
            "phone": self.f_phone.get().strip(),
            "email": self.f_email.get().strip(),
            "address": self.f_address.get().strip(),
            "notes": self.f_notes.get("1.0", "end").strip(),
        }
        try:
            if hasattr(self, "customer_id") and self.customer_id is not None:
                self.db.update_customer(self.customer_id, **data)
            else:
                pass
        except Exception:
            pass
        self.result = data
        self.destroy()


class SupplierDialog(ctk.CTkToplevel):
    def __init__(self, parent, db: Database, supplier_id: Optional[int] = None) -> None:
        super().__init__(parent)
        self.db = db
        self.result = False

        self.title("Edit supplier" if supplier_id else "New supplier")
        self.geometry("460x420")
        self.transient(parent); self.grab_set()

        frm = ctk.CTkFrame(self, corner_radius=10)
        frm.pack(fill="both", expand=True, padx=14, pady=14)
        frm.grid_columnconfigure(1, weight=1)

        row = 0
        ctk.CTkLabel(frm, text="Name *:").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        self.f_name = ctk.CTkEntry(frm); self.f_name.grid(row=row, column=1, sticky="ew", padx=10, pady=8)
        row += 1
        ctk.CTkLabel(frm, text="Phone:").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        self.f_phone = ctk.CTkEntry(frm); self.f_phone.grid(row=row, column=1, sticky="ew", padx=10, pady=8)
        row += 1
        ctk.CTkLabel(frm, text="Email:").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        self.f_email = ctk.CTkEntry(frm); self.f_email.grid(row=row, column=1, sticky="ew", padx=10, pady=8)
        row += 1
        ctk.CTkLabel(frm, text="Address:").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        self.f_address = ctk.CTkEntry(frm); self.f_address.grid(row=row, column=1, sticky="ew", padx=10, pady=8)
        row += 1
        ctk.CTkLabel(frm, text="Notes:").grid(row=row, column=0, sticky="nw", padx=10, pady=8)
        self.f_notes = ctk.CTkTextbox(frm, height=80)
        self.f_notes.grid(row=row, column=1, sticky="ew", padx=10, pady=8)
        row += 1

        btns = ctk.CTkFrame(frm, fg_color="transparent")
        btns.grid(row=row, column=0, columnspan=2, sticky="ew", padx=10, pady=14)
        btns.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(btns, text="Cancel", fg_color="gray", hover_color="dimgray", command=self.destroy).grid(
            row=0, column=0, sticky="ew", padx=4
        )
        ctk.CTkButton(btns, text="Save", command=self._save).grid(row=0, column=1, sticky="ew", padx=4)

        if supplier_id is not None:
            for s in self.db.list_suppliers():
                if s["id"] == supplier_id:
                    self.f_name.insert(0, s["name"])
                    if s["phone"]: self.f_phone.insert(0, s["phone"])
                    if s["email"]: self.f_email.insert(0, s["email"])
                    if s["address"]: self.f_address.insert(0, s["address"])
                    if s["notes"]: self.f_notes.insert("1.0", s["notes"])
                    self._existing_id = supplier_id
                    break
        else:
            self._existing_id = None

    def _save(self) -> None:
        name = self.f_name.get().strip()
        if not name:
            messagebox.showerror("Invalid", "Name is required."); return
        data = (
            name,
            self.f_phone.get().strip(),
            self.f_email.get().strip(),
            self.f_address.get().strip(),
            self.f_notes.get("1.0", "end").strip(),
        )
        try:
            if self._existing_id is not None:
                self.db.update_supplier(self._existing_id, *data)
            else:
                self.db.add_supplier(*data)
        except sqlite3.IntegrityError:
            messagebox.showerror("Duplicate", "A supplier with that name already exists."); return
        except sqlite3.Error as exc:
            messagebox.showerror("DB error", str(exc)); return
        self.result = True
        self.destroy()


class UserDialog(ctk.CTkToplevel):
    def __init__(self, parent, db: Database, user_id: Optional[int] = None) -> None:
        super().__init__(parent)
        self.db = db
        self.result = False

        self.title("Edit user" if user_id else "New user")
        self.geometry("440x380")
        self.transient(parent); self.grab_set()

        frm = ctk.CTkFrame(self, corner_radius=10)
        frm.pack(fill="both", expand=True, padx=14, pady=14)
        frm.grid_columnconfigure(1, weight=1)

        row = 0
        ctk.CTkLabel(frm, text="Username *:").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        self.f_username = ctk.CTkEntry(frm); self.f_username.grid(row=row, column=1, sticky="ew", padx=10, pady=8)
        row += 1
        ctk.CTkLabel(frm, text="Full name *:").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        self.f_name = ctk.CTkEntry(frm); self.f_name.grid(row=row, column=1, sticky="ew", padx=10, pady=8)
        row += 1
        ctk.CTkLabel(frm, text="Role *:").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        self.f_role = ctk.CTkComboBox(frm, values=[ROLE_ADMIN, ROLE_CASHIER], width=220)
        self.f_role.set(ROLE_CASHIER)
        self.f_role.grid(row=row, column=1, sticky="ew", padx=10, pady=8)
        row += 1
        ctk.CTkLabel(frm, text="Password *:").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        self.f_password = ctk.CTkEntry(frm, show="*")
        self.f_password.grid(row=row, column=1, sticky="ew", padx=10, pady=8)
        row += 1
        self.f_active = ctk.CTkCheckBox(frm, text="Active")
        self.f_active.select()
        self.f_active.grid(row=row, column=1, sticky="w", padx=10, pady=8)
        row += 1

        btns = ctk.CTkFrame(frm, fg_color="transparent")
        btns.grid(row=row, column=0, columnspan=2, sticky="ew", padx=10, pady=14)
        btns.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(btns, text="Cancel", fg_color="gray", hover_color="dimgray", command=self.destroy).grid(
            row=0, column=0, sticky="ew", padx=4
        )
        ctk.CTkButton(btns, text="Save", command=self._save).grid(row=0, column=1, sticky="ew", padx=4)

        self._existing_id = user_id
        if user_id is not None:
            for u in db.list_users():
                if u["id"] == user_id:
                    self.f_username.insert(0, u["username"])
                    self.f_username.configure(state="disabled")
                    self.f_name.insert(0, u["full_name"])
                    self.f_role.set(u["role"])
                    if not u["is_active"]:
                        self.f_active.deselect()
                    break
            self.f_password.configure(placeholder_text="(leave blank to keep)")
        else:
            self.f_password.configure(placeholder_text="min 4 characters")

    def _save(self) -> None:
        username = self.f_username.get().strip()
        full_name = self.f_name.get().strip()
        role = self.f_role.get()
        password = self.f_password.get()
        is_active = 1 if self.f_active.get() else 0

        if not username or not full_name:
            messagebox.showerror("Invalid", "Username and full name are required."); return
        if self._existing_id is None:
            if not password or len(password) < 4:
                messagebox.showerror("Invalid", "Password must be at least 4 characters."); return

        try:
            if self._existing_id is None:
                self.db.add_user(username, password, full_name, role)
            else:
                self.db.update_user(self._existing_id, full_name, role, is_active)
                if password:
                    if len(password) < 4:
                        messagebox.showerror("Invalid", "Password must be at least 4 characters."); return
                    self.db.reset_user_password(self._existing_id, password)
        except sqlite3.IntegrityError:
            messagebox.showerror("Duplicate", "That username is already taken."); return
        except sqlite3.Error as exc:
            messagebox.showerror("DB error", str(exc)); return
        self.result = True
        self.destroy()


class InvoiceDialog(ctk.CTkToplevel):
    def __init__(self, parent, db: Database, sale_id: int, invoice_number: str, read_only: bool = False) -> None:
        super().__init__(parent)
        self.db = db
        self.sale_id = sale_id
        self.invoice_number = invoice_number
        self.read_only = read_only

        self.title(f"Invoice {invoice_number}")
        self.geometry("640x720")
        self.transient(parent)
        if not read_only:
            self.grab_set()

        sale = db.get_sale(sale_id)
        if sale is None:
            self.destroy(); return
        items = db.get_sale_items(sale_id)
        settings = {
            "store_name": db.get_setting("store_name", "Detergent Warehouse"),
            "store_phone": db.get_setting("store_phone", ""),
            "store_address": db.get_setting("store_address", ""),
        }

        wrap = ctk.CTkFrame(self, corner_radius=10)
        wrap.pack(fill="both", expand=True, padx=14, pady=14)
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(wrap, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            head, text=settings["store_name"], font=ctk.CTkFont(size=18, weight="bold")
        ).grid(row=0, column=0, sticky="w")
        if settings["store_phone"]:
            ctk.CTkLabel(head, text=f"📞 {settings['store_phone']}", text_color="gray50").grid(
                row=1, column=0, sticky="w"
            )
        if settings["store_address"]:
            ctk.CTkLabel(head, text=settings["store_address"], text_color="gray50",
                         wraplength=600, justify="left").grid(row=2, column=0, sticky="w")
        ctk.CTkLabel(
            head, text=f"INVOICE  •  {invoice_number}",
            font=ctk.CTkFont(size=14, weight="bold"), text_color="#1d6f42",
        ).grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(head, text=fmt_date(sale["created_at"]), text_color="gray50").grid(
            row=1, column=1, sticky="e"
        )

        info = ctk.CTkFrame(wrap, fg_color="transparent")
        info.grid(row=0, column=0, sticky="ew", padx=8, pady=4)

        text = ctk.CTkTextbox(wrap, font=ctk.CTkFont(size=12, family="Courier"))
        text.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)

        line = "═" * 64
        sep = "─" * 64
        out = io.StringIO()
        out.write(f"  Cashier: {sale['user_name'] or '-'}\n")
        out.write(f"  Customer: {sale['customer_name'] or 'Walk-in'}\n")
        out.write(f"  Payment: {sale['payment_method']}\n\n")
        out.write(f"  {'Item':<32}{'Qty':>6}{'Unit':>12}{'Total':>14}\n")
        out.write(f"  {sep}\n")
        for it in items:
            out.write(
                f"  {it['product_name'][:31]:<32}{it['quantity']:>6}"
                f"{it['unit_price']:>12.2f}{it['line_total']:>14.2f}\n"
            )
        out.write(f"  {sep}\n")
        out.write(f"  {'Subtotal':<50}{sale['subtotal']:>14.2f}\n")
        if sale["discount"]:
            out.write(f"  {'Discount':<50}{-sale['discount']:>14.2f}\n")
        if sale["tax"]:
            out.write(f"  {'Tax':<50}{sale['tax']:>14.2f}\n")
        out.write(f"  {line}\n")
        out.write(f"  {'TOTAL':<50}{sale['total']:>14.2f} {CURRENCY}\n")
        out.write(f"  {line}\n")
        out.write(f"  {'Paid':<50}{sale['amount_paid']:>14.2f}\n")
        out.write(f"  {'Change':<50}{sale['change_given']:>14.2f}\n\n")
        out.write("  Thank you for your business!\n")

        text.insert("1.0", out.getvalue())
        text.configure(state="disabled")

        btns = ctk.CTkFrame(wrap, fg_color="transparent")
        btns.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 8))
        ctk.CTkButton(btns, text="🖨 Print", command=self._print).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="💾 Save TXT", command=self._save_txt).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="📄 Save PDF", fg_color="#1d6f42", hover_color="#155232",
                      command=self._save_pdf).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="Close", fg_color="gray", hover_color="dimgray",
                      command=self.destroy).pack(side="right", padx=4)

    def _build_invoice_text(self) -> str:
        sale = self.db.get_sale(self.sale_id)
        items = self.db.get_sale_items(self.sale_id)
        if sale is None:
            return ""
        settings = {
            "store_name": self.db.get_setting("store_name", "Detergent Warehouse"),
            "store_phone": self.db.get_setting("store_phone", ""),
            "store_address": self.db.get_setting("store_address", ""),
        }
        line = "=" * 48
        sep = "-" * 48
        out = io.StringIO()
        out.write(f"{settings['store_name'].center(48)}\n")
        if settings["store_phone"]:
            out.write(f"{settings['store_phone'].center(48)}\n")
        if settings["store_address"]:
            out.write(f"{settings['store_address'].center(48)}\n")
        out.write(f"{line}\n")
        out.write(f"INVOICE: {sale['invoice_number']}\n")
        out.write(f"Date:    {fmt_date(sale['created_at'])}\n")
        out.write(f"Cashier: {sale['user_name'] or '-'}\n")
        out.write(f"Customer:{sale['customer_name'] or 'Walk-in'}\n")
        out.write(f"{sep}\n")
        out.write(f"{'Item':<24}{'Qty':>5}{'Unit':>9}{'Total':>10}\n")
        out.write(f"{sep}\n")
        for it in items:
            out.write(
                f"{it['product_name'][:23]:<24}{it['quantity']:>5}"
                f"{it['unit_price']:>9.2f}{it['line_total']:>10.2f}\n"
            )
        out.write(f"{sep}\n")
        out.write(f"{'Subtotal':<38}{sale['subtotal']:>10.2f}\n")
        if sale["discount"]:
            out.write(f"{'Discount':<38}{-sale['discount']:>10.2f}\n")
        if sale["tax"]:
            out.write(f"{'Tax':<38}{sale['tax']:>10.2f}\n")
        out.write(f"{line}\n")
        out.write(f"{'TOTAL':<38}{sale['total']:>10.2f} {CURRENCY}\n")
        out.write(f"{line}\n")
        out.write(f"{'Paid':<38}{sale['amount_paid']:>10.2f}\n")
        out.write(f"{'Change':<38}{sale['change_given']:>10.2f}\n")
        out.write(f"\n{'Thank you for your business!'.center(48)}\n")
        return out.getvalue()

    def _print(self) -> None:
        try:
            import tempfile
            tmp = os.path.join(tempfile.gettempdir(), f"{self.invoice_number}.txt")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(self._build_invoice_text())
            if sys.platform.startswith("win"):
                os.startfile(tmp, "print")
            else:
                os.system(f"lp '{tmp}' 2>/dev/null || lpr '{tmp}' 2>/dev/null || xdg-open '{tmp}'")
        except Exception as exc:
            messagebox.showerror("Print failed", str(exc))

    def _save_txt(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("Text", "*.txt")],
            initialfile=f"{self.invoice_number}.txt",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._build_invoice_text())
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc)); return
        messagebox.showinfo("Saved", f"Invoice saved to:\n{path}")

    def _save_pdf(self) -> None:
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
        except ImportError:
            messagebox.showerror("Missing dependency", "Install reportlab:\npip install reportlab")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF", "*.pdf")],
            initialfile=f"{self.invoice_number}.pdf",
        )
        if not path:
            return
        sale = self.db.get_sale(self.sale_id)
        items = self.db.get_sale_items(self.sale_id)
        if sale is None:
            return
        try:
            c = canvas.Canvas(path, pagesize=A4)
            w, h = A4
            y = h - 50
            store_name = self.db.get_setting("store_name", "Detergent Warehouse")
            store_phone = self.db.get_setting("store_phone", "")
            store_address = self.db.get_setting("store_address", "")
            c.setFont("Helvetica-Bold", 18); c.drawCentredString(w / 2, y, store_name); y -= 22
            if store_phone:
                c.setFont("Helvetica", 10); c.drawCentredString(w / 2, y, store_phone); y -= 14
            if store_address:
                c.drawCentredString(w / 2, y, store_address); y -= 14
            c.line(40, y, w - 40, y); y -= 20
            c.setFont("Helvetica-Bold", 13); c.drawString(40, y, f"INVOICE  {sale['invoice_number']}"); y -= 18
            c.setFont("Helvetica", 10)
            c.drawString(40, y, f"Date:    {fmt_date(sale['created_at'])}"); y -= 14
            c.drawString(40, y, f"Cashier: {sale['user_name'] or '-'}"); y -= 14
            c.drawString(40, y, f"Customer:{sale['customer_name'] or 'Walk-in'}"); y -= 14
            c.drawString(40, y, f"Payment: {sale['payment_method']}"); y -= 18
            c.line(40, y, w - 40, y); y -= 16
            c.setFont("Helvetica-Bold", 10)
            c.drawString(40, y, "Item"); c.drawRightString(300, y, "Qty")
            c.drawRightString(380, y, "Unit")
            c.drawRightString(w - 40, y, "Total")
            y -= 14
            c.setFont("Helvetica", 10)
            for it in items:
                if y < 80:
                    c.showPage(); y = h - 50
                c.drawString(40, y, it["product_name"][:40])
                c.drawRightString(300, y, str(it["quantity"]))
                c.drawRightString(380, y, f"{it['unit_price']:.2f}")
                c.drawRightString(w - 40, y, f"{it['line_total']:.2f}")
                y -= 14
            c.line(40, y, w - 40, y); y -= 14
            c.drawString(40, y, "Subtotal"); c.drawRightString(w - 40, y, f"{sale['subtotal']:.2f} {CURRENCY}"); y -= 14
            if sale["discount"]:
                c.drawString(40, y, "Discount"); c.drawRightString(w - 40, y, f"-{sale['discount']:.2f} {CURRENCY}"); y -= 14
            if sale["tax"]:
                c.drawString(40, y, "Tax"); c.drawRightString(w - 40, y, f"{sale['tax']:.2f} {CURRENCY}"); y -= 14
            c.setFont("Helvetica-Bold", 12)
            c.drawString(40, y, "TOTAL"); c.drawRightString(w - 40, y, f"{sale['total']:.2f} {CURRENCY}"); y -= 18
            c.setFont("Helvetica", 10)
            c.drawString(40, y, "Paid"); c.drawRightString(w - 40, y, f"{sale['amount_paid']:.2f} {CURRENCY}"); y -= 14
            c.drawString(40, y, "Change"); c.drawRightString(w - 40, y, f"{sale['change_given']:.2f} {CURRENCY}"); y -= 30
            c.setFont("Helvetica-Oblique", 9)
            c.drawCentredString(w / 2, y, "Thank you for your business!")
            c.save()
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc)); return
        except Exception as exc:
            messagebox.showerror("PDF error", str(exc)); return
        messagebox.showinfo("Saved", f"PDF saved to:\n{path}")


def main() -> int:
    db_path = os.path.join(resource_dir(), "warehouse.db")
    db = Database(db_path)

    def start_app(user: sqlite3.Row) -> None:
        app = WarehouseApp(db, user)
        app.protocol("WM_DELETE_WINDOW", app.on_closing)
        app.mainloop()

    login = LoginWindow(db, on_success=start_app)
    login.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
