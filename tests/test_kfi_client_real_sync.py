"""실 API 모드(USE_MOCK=false)의 sync/실시간조회 로직을, 확인된 데이터셋 스펙과 동일한 형태의
스텁 응답으로 검증한다 (Node판 kfi_sync_stub_test.js와 동일한 목적)."""
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


STUB_PAGES = {
    "opnFsuplAprv01": {
        "resultCode": "00", "resultMsg": "NORMAL_CODE", "numOfRows": 2, "pageNo": 1, "totalCount": 2,
        "items": [
            {"cmpyNm": "(주)한국소방기기", "gdsNm": "분말소화기", "ctfcnNo": "형식승인 제2022-3-045호", "aprvYmd": "20220512"},
            {"cmpyNm": "대한안전산업(주)", "gdsNm": "리튬이온전지 전용소화기", "ctfcnNo": "성능인증 제2023-7-118호", "aprvYmd": "20230901"},
        ],
    },
    "opnFsuplRtrcn01": {
        "resultCode": "00", "resultMsg": "NORMAL_CODE", "numOfRows": 1, "pageNo": 1, "totalCount": 1,
        "items": [
            {"cmpyNm": "대한안전산업(주)", "ctfcnNo": "성능인증 제2023-7-118호", "rtrcnYmd": "2026-08-01",
             "ctfcnFomNm": "리튬이온전지 전용소화기", "dspsCn": "소화성능 재검증 결과 기준 미달"},
        ],
    },
    "opnApiMnfcCmpy01": {
        "resultCode": "00", "resultMsg": "NORMAL_CODE", "numOfRows": 1, "pageNo": 1, "totalCount": 1,
        "items": [{"cmpyNm": "(주)한국소방기기", "rprsvNm": "홍길동", "adres": "서울시 어딘가", "telno": "02-000-0000"}],
    },
    "opnGcExsrImpmAply02": {
        "resultCode": "00", "resultMsg": "NORMAL_CODE", "numOfRows": 1, "pageNo": 1, "totalCount": 1,
        "items": [{"exsrImpmCmpyNm": "부산소방정비(주)", "exsrImpmYmd": "20240501", "psmrkPrfcNo": "BC CN-03944",
                    "exagQtyCn": "3.3", "exsrImpmYrNo": "2024-1832"}],
    },
}


def fake_get(url, params=None, timeout=None):
    assert params.get("ServiceKey") == "TESTKEY", "ServiceKey가 요청에 포함되어야 함"
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
