"""실 API 모드(USE_MOCK=false)의 sync/실시간조회 로직을, 확인된 데이터셋 스펙과 동일한 형태의
스텁 응답으로 검증한다 (Node판 kfi_sync_stub_test.js와 동일한 목적).

스텁 형태는 KFI가 공식 배포한 "OpenAPI활용가이드_소방산업기술원_소방용품업체정보.docx"의 실제
요청/응답 예제를 그대로 반영한다: 파라미터명은 소문자 "serviceKey", 응답은
{"data": [...], "header": {"resultCode":"00", ...}} 구조이며 업체 필드는 rprsvPnm/fctryAdr/
fctryTelno다(과거에는 이 스텁이 잘못된 추정 구조를 썼었고, 그 결과 실서비스 코드도 같은
잘못된 구조를 가정하고 있었다 — 그래서 실 배포에서 조용히 0건만 동기화되는 버그로 이어졌다)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["DB_PATH"] = ":memory:"
os.environ["USE_MOCK"] = "false"
os.environ["KFI_SERVICE_KEY"] = "TESTKEY"

import db as db_module
db_module.reset_conn()
import kfi_client as kfi
import requests


class FakeResponse:
    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


def _envelope(rows, total=None):
    return {
        "data": rows,
        "header": {"pageNo": "1", "resultCode": "00", "resultMsg": "NORMAL_CODE",
                    "numOfRows": len(rows), "totalCount": total if total is not None else len(rows)},
    }


STUB_PAGES = {
    "opnFsuplAprv01": _envelope([
        {"cmpyNm": "(주)한국소방기기", "gdsNm": "분말소화기", "ctfcnNo": "형식승인 제2022-3-045호", "aprvYmd": "20220512"},
        {"cmpyNm": "대한안전산업(주)", "gdsNm": "리튬이온전지 전용소화기", "ctfcnNo": "성능인증 제2023-7-118호", "aprvYmd": "20230901"},
    ]),
    "opnFsuplRtrcn01": _envelope([
        {"cmpyNm": "대한안전산업(주)", "ctfcnNo": "성능인증 제2023-7-118호", "rtrcnYmd": "2026-08-01",
         "ctfcnFomNm": "리튬이온전지 전용소화기", "dspsCn": "소화성능 재검증 결과 기준 미달"},
    ]),
    # 필드명(rprsvPnm/fctryAdr/fctryTelno)은 KFI 공식 활용가이드의 실제 응답 예제와 동일하다.
    "opnApiMnfcCmpy01": _envelope([
        {"cmpyNm": "(주)한국소방기기", "rprsvPnm": "홍길동", "hmpgUrlAdr": None,
         "fctryAdr": "서울시 어딘가", "fctryTelno": "02-000-0000", "gdsNm": "분말소화기"},
    ]),
    "opnGcExsrImpmAply02": _envelope([
        {"exsrImpmCmpyNm": "부산소방정비(주)", "exsrImpmYmd": "20240501", "psmrkPrfcNo": "BC CN-03944",
         "exagQtyCn": "3.3", "exsrImpmYrNo": "2024-1832"},
    ]),
}


def fake_get(url, params=None, timeout=None):
    # 활용가이드 실제 요청 예제(...?serviceKey=인증키...)는 파라미터명이 소문자다.
    assert params.get("serviceKey") == "TESTKEY", "serviceKey(소문자)가 요청에 포함되어야 함"
    for key, body in STUB_PAGES.items():
        if url.endswith(key):
            return FakeResponse(body)
    # 02/03(성능인증/KFI인정) 등 아직 스텁이 없는 엔드포인트는 일부러 실패시켜 에러 핸들링 검증
    raise requests.exceptions.ConnectionError("no stub for " + url)


def setup_function():
    db_module.reset_conn()


def test_sync_approvals_parses_and_upserts(monkeypatch):
    monkeypatch.setattr(kfi, "USE_MOCK", False)
    monkeypatch.setattr(kfi, "SERVICE_KEY", "TESTKEY")
    monkeypatch.setattr(requests, "get", fake_get)
    result = kfi.sync_approvals(from_aprv="20020101", to_aprv="20260805", gds_cl_codes=["01"])
    assert result["synced"] == 2
    # opnFsuplAprv02/03은 스텁이 없어 에러로 잡히고 계속 진행되어야 함(서버가 죽으면 안 됨)
    assert len(result["errors"]) == 2


def test_sync_cancellations_updates_cache(monkeypatch):
    monkeypatch.setattr(kfi, "USE_MOCK", False)
    monkeypatch.setattr(kfi, "SERVICE_KEY", "TESTKEY")
    monkeypatch.setattr(requests, "get", fake_get)
    kfi.sync_approvals(from_aprv="20020101", to_aprv="20260805", gds_cl_codes=["01"])
    result = kfi.sync_cancellations(from_aprv="20020101", to_aprv="20260805", gds_cl_codes=["01"])
    assert result["synced"] == 1
    approval = kfi.get_approval("성능인증 제2023-7-118호")
    assert approval["status"] == "cancelled"
    assert approval["cancel"]["reason"] == "소화성능 재검증 결과 기준 미달"


def test_sync_companies(monkeypatch):
    monkeypatch.setattr(kfi, "USE_MOCK", False)
    monkeypatch.setattr(kfi, "SERVICE_KEY", "TESTKEY")
    monkeypatch.setattr(requests, "get", fake_get)
    result = kfi.sync_companies(gds_cl_codes=["01"])
    assert result["synced"] == 1
    company = kfi.find_company("한국소방기기")
    assert company["rep"] == "홍길동"


def test_fetch_maintenance_by_unit_realtime(monkeypatch):
    monkeypatch.setattr(kfi, "USE_MOCK", False)
    monkeypatch.setattr(kfi, "SERVICE_KEY", "TESTKEY")
    monkeypatch.setattr(requests, "get", fake_get)
    maint = kfi.fetch_maintenance_by_unit("BC CN-03944")
    assert len(maint) == 1
    assert maint[0]["company"] == "부산소방정비(주)"
    assert maint[0]["maintNo"] == "2024-1832"
