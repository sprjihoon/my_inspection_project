import sqlite3
import os
from datetime import datetime

DB_PATH = "inspection_data.db"


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def ensure_column_exists(table, column, col_type):
    con = get_connection()
    cur = con.cursor()
    cols = cur.execute(f"PRAGMA table_info({table})").fetchall()
    col_names = [c[1] for c in cols]
    if column not in col_names:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        con.commit()
    con.close()


def init_db():
    con = get_connection()
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE,
      password TEXT,
      role TEXT,
      created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS products (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      product_name TEXT,
      vendor_id INT,
      operator_id INT,
      main_image TEXT,
      location TEXT,
      created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS inspection_results (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      product_id INT,
      inspector_id INT,
      defect_qty INT DEFAULT 0,
      normal_qty INT DEFAULT 0,
      pending_qty INT DEFAULT 0,
      total_qty INT DEFAULT 0,
      comment TEXT,
      inspected_at TEXT,
      status TEXT,
      similarity_pct REAL,
      barcode TEXT,
      operator TEXT,
      image_name TEXT
    );

    CREATE TABLE IF NOT EXISTS work_orders (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      inspection_id INT,
      worker_id INT,
      additional_defect_qty INT DEFAULT 0,
      repaired_qty INT DEFAULT 0,
      repaired_approved INT DEFAULT 0,
      difficulty TEXT,
      extra_tasks TEXT,
      created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS activity_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INT,
      action_type TEXT,
      table_name TEXT,
      record_id INT,
      old_data TEXT,
      new_data TEXT,
      created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS receipts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      vendor_id INT,
      operator_id INT,
      receipt_file TEXT,
      uploaded_by INT,
      status TEXT DEFAULT 'active',
      created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS product_images (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      product_id INT,
      image_path TEXT,
      is_main INTEGER DEFAULT 0,
      uploaded_at TEXT
    );

    CREATE TABLE IF NOT EXISTS skus (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      product_id INT,
      barcode TEXT,
      vendor TEXT,
      status TEXT,
      created_at TEXT,
      color TEXT DEFAULT '',
      size TEXT DEFAULT ''
    );
    """)
    con.commit()

    ensure_column_exists("inspection_results", "inspected_at", "TEXT")
    ensure_column_exists("inspection_results", "status", "TEXT")
    ensure_column_exists("inspection_results", "barcode", "TEXT")
    ensure_column_exists("skus", "color", "TEXT")
    ensure_column_exists("skus", "size", "TEXT")

    count = cur.execute("SELECT count(*) FROM users").fetchone()[0]
    if count == 0:
        cur.executescript(f"""
        INSERT INTO users(username, password, role, created_at) VALUES
        ('admin','admin','admin','{now_str()}'),
        ('op1','op1','operator','{now_str()}'),
        ('insp1','insp1','inspector','{now_str()}'),
        ('worker1','worker1','worker','{now_str()}');
        """)
        con.commit()
    con.close()


def log_activity(user_id, action_type, table_name, record_id, old_data, new_data):
    con = get_connection()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO activity_log(user_id, action_type, table_name, record_id, old_data, new_data, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, action_type, table_name, record_id, old_data, new_data, now_str()))
    con.commit()
    con.close()
