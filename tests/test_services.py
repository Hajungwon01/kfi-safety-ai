import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["DB_PATH"] = ":memory:"
os.environ["USE_MOCK"] = "true"

import db as db_module
db_module.reset_conn()

import auth
import kfi_client as kfi
from services import report_service, notification_service, recall_service


def setup_function():
    db_module.reset_conn()


def test_report_submit_and_stats():
    u, _ = auth.register_user("r@example.com", "pw1234")
    report_service.submit_report(u["id"], "fraud", "서울특별시", "대상", "사유", "위험")
    s = report_service.stats()
    assert s["fraud"] == 1
    rows = report_service.list_reports()
    assert len(rows) == 1


def test_recall_simulation_full_flow():
    u, _ = auth.register_user("locker@example.com", "pw1234")
    unit = kfi.get_unit("EYTN-52981")
    assert unit is not None
    conn = db_module.get_conn()
    conn.execute("INSERT INTO registered_units (user_id, unit_code) VALUES (?,?)", (u["id"], "EYTN-52981"))
    conn.commit()

    result = recall_service.simulate_recall()
    assert result.get("ok") is True
    assert result["notified"] == 1

    approval = kfi.get_approval("성능인증 제2023-7-118호")
    assert approval["status"] == "cancelled"

    notifs = notification_service.list_mine(u["id"])
    assert len(notifs) == 1
    assert "리콜" in notifs[0]["message"]

    # 중복 트리거 방지
    dup = recall_service.simulate_recall()
    assert "error" in dup


def test_unit_service_evaluate_and_register_and_list():
    from services import unit_service
    u, _ = auth.register_user("unit@example.com", "pw1234")
    ev = unit_service.evaluate_by_code("BQKD-88213")
    assert ev["found"] is True
    assert ev["grade"] == "안전"
    reg = unit_service.register_unit(u["id"], "BQKD-88213")
    assert reg["ok"] is True
    mine = unit_service.list_mine(u["id"])
    assert len(mine) == 1
    assert mine[0]["unit"]["code"] == "BQKD-88213"


def test_unit_service_not_found():
    from services import unit_service
    ev = unit_service.evaluate_by_code("NOPE-00000")
    assert ev["found"] is False
