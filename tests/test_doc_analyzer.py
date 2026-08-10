import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from doc_analyzer import analyze_document


def test_high_risk_scam_text():
    text = "리튬이온 전용 소화기를 즉시 비치하지 않으면 과태료가 부과됩니다. 오늘까지 계좌로 입금 바랍니다."
    r = analyze_document(text)
    assert r["level"] == "고위험"
    assert r["score"] >= 60
    assert len(r["snippets"]) > 0


def test_legit_notice_is_low_risk():
    text = "본 문서는 2026년 리튬이온 전용소화기 비치 안내문(제2026-118호)입니다. 관할 소방서(02-000-0000)로 문의 바랍니다."
    r = analyze_document(text)
    assert r["level"] == "저위험"
