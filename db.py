"""SQLite 데이터 계층 (Python 내장 sqlite3 사용)."""
import json
import os
import sqlite3
import bcrypt
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
DB_PATH = os.environ.get("DB_PATH", str(BASE_DIR / "data" / "app.db"))

# 관제 대시보드는 관리자 전용이라, 데모에서도 실제로 로그인해서 써볼 수 있도록
# 고정된 관리자 계정을 서버 시작 시 시딩한다. 일반 회원가입으로는 이 role을 가질 수 없다.
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@kfi.go.kr")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin1234!")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'citizen',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS approval_cache (
  number TEXT PRIMARY KEY,
  type TEXT, item TEXT, company TEXT, approved_date TEXT,
  cancelled INTEGER NOT NULL DEFAULT 0,
  cancel_date TEXT, cancel_reason TEXT,
  synced_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS companies (
  name TEXT PRIMARY KEY, role TEXT, rep TEXT, address TEXT, phone TEXT
);

CREATE TABLE IF NOT EXISTS units (
  code TEXT PRIMARY KEY,
  item TEXT, first_approved TEXT, maker TEXT
);

CREATE TABLE IF NOT EXISTS maintenance_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  unit_code TEXT NOT NULL,
  company TEXT, date TEXT, amount TEXT, maint_no TEXT
);

CREATE TABLE IF NOT EXISTS registered_units (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  unit_code TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(user_id, unit_code)
);

CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  type TEXT NOT NULL,
  region TEXT, target TEXT, reason TEXT, risk_level TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  unit_code TEXT,
  message TEXT NOT NULL,
  is_read INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_conn = None


def get_conn():
    """전역 커넥션을 하나 유지 (Streamlit 세션마다 새로 열지 않도록)."""
    global _conn
    if _conn is None:
        Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True) if DB_PATH != ":memory:" else None
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
        _conn.commit()
        _seed_if_empty(_conn)
        _seed_admin(_conn)
    return _conn


def _seed_admin(conn):
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (ADMIN_EMAIL,)).fetchone()
    if existing:
        return
    pw_hash = bcrypt.hashpw(ADMIN_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    conn.execute(
        "INSERT INTO users (email, password_hash, role) VALUES (?,?,?)",
        (ADMIN_EMAIL, pw_hash, "admin"),
    )
    conn.commit()


def reset_conn():
    """테스트 전용: 전역 커넥션을 초기화해서 다음 get_conn()이 새로 만들게 한다."""
    global _conn
    if _conn is not None:
        _conn.close()
    _conn = None


def _seed_if_empty(conn):
    mock_dir = BASE_DIR / "data" / "mock"
    if conn.execute("SELECT COUNT(*) c FROM approval_cache").fetchone()["c"] == 0:
        approvals = json.loads((mock_dir / "approvals.json").read_text(encoding="utf-8"))
        conn.executemany(
            "INSERT INTO approval_cache (number,type,item,company,approved_date) VALUES (?,?,?,?,?)",
            [(a["number"], a["type"], a["item"], a["company"], a["approvedDate"]) for a in approvals],
        )
    if conn.execute("SELECT COUNT(*) c FROM companies").fetchone()["c"] == 0:
        companies = json.loads((mock_dir / "companies.json").read_text(encoding="utf-8"))
        conn.executemany(
            "INSERT INTO companies (name,role,rep,address,phone) VALUES (?,?,?,?,?)",
            [(c["name"], c["role"], c["rep"], c["address"], c["phone"]) for c in companies],
        )
    if conn.execute("SELECT COUNT(*) c FROM units").fetchone()["c"] == 0:
        units = json.loads((mock_dir / "units.json").read_text(encoding="utf-8"))
        conn.executemany(
            "INSERT INTO units (code,item,first_approved,maker) VALUES (?,?,?,?)",
            [(u["code"], u["item"], u["firstApproved"], u["maker"]) for u in units],
        )
    if conn.execute("SELECT COUNT(*) c FROM maintenance_records").fetchone()["c"] == 0:
        records = json.loads((mock_dir / "maintenance.json").read_text(encoding="utf-8"))
        conn.executemany(
            "INSERT INTO maintenance_records (unit_code,company,date,amount,maint_no) VALUES (?,?,?,?,?)",
            [(r["unitCode"], r["company"], r["date"], r["amount"], r["maintNo"]) for r in records],
        )
    conn.commit()
