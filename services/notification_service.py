"""알림 서비스 (Node판 routes/notifications.js + services/recallWatcher.js 포팅)."""
import db as db_module


def notify_affected_users(approval_number: str, item_text: str, reason: str) -> dict:
    """item 텍스트가 일치하는 유닛들을 찾아, 그 유닛을 등록한 사용자에게 알림을 기록한다.
    (근사 매칭 - 개별유닛에는 승인번호 직결 데이터가 없어 형식명으로 매칭)"""
    conn = db_module.get_conn()
    units = conn.execute("SELECT code FROM units WHERE item = ?", (item_text,)).fetchall()
    if not units:
        return {"notified": 0, "units": []}
    codes = [u["code"] for u in units]
    placeholders = ",".join("?" for _ in codes)
    regs = conn.execute(
        f"SELECT DISTINCT user_id, unit_code FROM registered_units WHERE unit_code IN ({placeholders})", codes
    ).fetchall()
    for r in regs:
        msg = (f"🔔 등록하신 소화기({r['unit_code']}, {item_text})의 인증({approval_number})이 "
               f"리콜(승인취소)되었습니다. 사유: {reason}. 점검·교체를 권장합니다.")
        conn.execute("INSERT INTO notifications (user_id, unit_code, message) VALUES (?,?,?)", (r["user_id"], r["unit_code"], msg))
    conn.commit()
    return {"notified": len(regs), "units": [r["unit_code"] for r in regs]}


def list_mine(user_id: int) -> list[dict]:
    conn = db_module.get_conn()
    rows = conn.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()
    return [dict(r) for r in rows]
