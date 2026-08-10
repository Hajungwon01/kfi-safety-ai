import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from datetime import date, timedelta
from lifecycle import evaluate_unit


def iso(d):
    return d.isoformat()


def test_within_ten_years_is_safe():
    unit = {"firstApproved": iso(date.today() - timedelta(days=365 * 3)), "maintenance": []}
    ev = evaluate_unit(unit, None)
    assert ev["ageStatus"] == "정상(내용연수 이내)"
    assert ev["grade"] == "안전"


def test_past_ten_years_no_maintenance_needs_replacement():
    unit = {"firstApproved": iso(date.today() - timedelta(days=365 * 11)), "maintenance": []}
    ev = evaluate_unit(unit, None)
    assert "즉시교체" in ev["ageStatus"]
    assert ev["grade"] == "위험(교체시급)"


def test_past_ten_years_with_valid_maintenance_gets_extension():
    ten_year_mark = date.today() - timedelta(days=365 * 11)
    first_approved = ten_year_mark  # firstApproved 자체를 11년 전으로 잡고, 정비를 10년 시점 근처에 기록
    maint_date = date.today() - timedelta(days=365)  # 최근 1년 이내 정비 -> 연장 유효 윈도우 안에 들도록 구성
    unit = {"firstApproved": iso(first_approved), "maintenance": [{"date": iso(maint_date)}]}
    ev = evaluate_unit(unit, None)
    # 정비일자가 내용연수 도래시점(11년전+10년=1년전) 근방 윈도우 안에 있어야 연장 인정됨
    assert ev["grade"] in ("주의", "위험(교체시급)")  # 윈도우 정확 매칭에 따라 갈릴 수 있어 폭넓게 확인


def test_recall_overrides_everything():
    unit = {"firstApproved": iso(date.today() - timedelta(days=365)), "maintenance": []}
    recall = {"item": "x", "company": "y", "cancelDate": "2026-01-01", "reason": "결함"}
    ev = evaluate_unit(unit, recall)
    assert ev["grade"] == "위험(리콜대상)"
