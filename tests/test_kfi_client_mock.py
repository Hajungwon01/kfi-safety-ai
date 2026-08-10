import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["DB_PATH"] = ":memory:"
os.environ["USE_MOCK"] = "true"

import db as db_module
db_module.reset_conn()
import kfi_client as kfi


def setup_function():
    db_module.reset_conn()
    os.environ["USE_MOCK"] = "true"
    kfi.USE_MOCK = True


def test_get_approval_valid():
    r = kfi.get_approval("형식승인 제2022-3-045호")
    assert r["status"] == "valid"
    assert r["data"]["company"] == "(주)한국소방기기"


def test_get_approval_unregistered():
    r = kfi.get_approval("형식승인 제2099-9-999호")
    assert r["status"] == "unregistered"


def test_find_company_fuzzy_match():
    c = kfi.find_company("한국소방기기")
    assert c is not None
    c2 = kfi.find_company("가짜소방유통")
    assert c2 is None


def test_get_unit_and_evaluate():
    from lifecycle import evaluate_unit
    unit = kfi.get_unit("EYTN-52981")
    assert unit is not None
    assert unit["item"] == "리튬이온전지 전용소화기"
    recall = kfi.find_recall_by_item_text(unit["item"])
    assert recall is None
    ev = evaluate_unit(unit, None)
    assert ev["grade"] == "안전"


def test_recall_flow_updates_locker_and_approval():
    kfi.mark_approval_cancelled("성능인증 제2023-7-118호", "소화성능 재검증 결과 기준 미달")
    approval = kfi.get_approval("성능인증 제2023-7-118호")
    assert approval["status"] == "cancelled"
    unit = kfi.get_unit("EYTN-52981")
    recall = kfi.find_recall_by_item_text(unit["item"])
    assert recall is not None
    from lifecycle import evaluate_unit
    ev = evaluate_unit(unit, recall)
    assert ev["grade"] == "위험(리콜대상)"
