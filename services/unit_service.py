"""합격표시번호(개별 유닛) 평가 + 등록 (Node판 routes/units.js의 evaluateByCode 포팅)."""
import db as db_module
import kfi_client as kfi
from lifecycle import evaluate_unit


def evaluate_by_code(code: str) -> dict:
    unit = kfi.get_unit(code)
    if not unit:
        return {"found": False}
    recall = kfi.find_recall_by_item_text(unit["item"])
    recall_arg = None
    if recall:
        recall_arg = {"item": recall["item"], "company": recall["company"], "cancelDate": recall["cancel_date"], "reason": recall["cancel_reason"]}
    ev = evaluate_unit(
        {"firstApproved": unit["firstApproved"], "maintenance": [{"date": m["date"]} for m in unit["maintenance"]]},
        recall_arg,
    )
    return {"found": True, "unit": unit, **ev}


def register_unit(user_id: int, code: str) -> dict:
    ev = evaluate_by_code(code)
    if not ev["found"]:
        return {"error": "등록된 소화기 정보를 찾을 수 없습니다."}
    conn = db_module.get_conn()
    conn.execute("INSERT OR IGNORE INTO registered_units (user_id, unit_code) VALUES (?,?)", (user_id, ev["unit"]["code"]))
    conn.commit()
    return {"ok": True, "unit": ev}


def list_mine(user_id: int) -> list[dict]:
    conn = db_module.get_conn()
    rows = conn.execute("SELECT unit_code FROM registered_units WHERE user_id=?", (user_id,)).fetchall()
    return [evaluate_by_code(r["unit_code"]) for r in rows]
