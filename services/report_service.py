"""신고 접수 서비스 (Node판 routes/reports.js 포팅)."""
import db as db_module


def submit_report(user_id, type_, region, target, reason, risk_level):
    if type_ not in ("fraud", "maintenance"):
        raise ValueError("type은 fraud 또는 maintenance여야 합니다.")
    conn = db_module.get_conn()
    cur = conn.execute(
        "INSERT INTO reports (user_id, type, region, target, reason, risk_level) VALUES (?,?,?,?,?,?)",
        (user_id, type_, region or "기타 지역", target or "", reason or "", risk_level or "위험"),
    )
    conn.commit()
    return cur.lastrowid


def list_reports(limit=50):
    conn = db_module.get_conn()
    rows = conn.execute("SELECT * FROM reports ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def stats():
    conn = db_module.get_conn()
    fraud = conn.execute("SELECT COUNT(*) c FROM reports WHERE type='fraud'").fetchone()["c"]
    maint = conn.execute("SELECT COUNT(*) c FROM reports WHERE type='maintenance'").fetchone()["c"]
    by_region = conn.execute("SELECT region, COUNT(*) c FROM reports GROUP BY region").fetchall()
    return {"fraud": fraud, "maintenance": maint, "byRegion": [dict(r) for r in by_region]}
