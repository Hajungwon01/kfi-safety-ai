"""KFI 공공데이터 어댑터 (Node판 kfiClient.js 포팅).
USE_MOCK=true(기본): db가 시딩한 mock 데이터로 동작.
USE_MOCK=false + KFI_SERVICE_KEY: data.go.kr 실 API로 캐시 테이블을 동기화(sync)해서 채움.

중요한 설계상 제약(Node판과 동일): 이 API들은 "승인번호로 1건 조회" 단건조회를 지원하지 않고
날짜범위(fromAprv~toAprv)+품목분류코드(gdsClCd) 기준의 "목록조회(페이징)"만 지원한다.
예외적으로 "정비번호 발급현황"만 합격표시번호로 단건조회가 가능하다.
"""
import os
import requests
from datetime import date
import db as db_module

USE_MOCK = os.environ.get("USE_MOCK", "true").lower() != "false"
SERVICE_KEY = os.environ.get("KFI_SERVICE_KEY", "")
GDS_CL_CODES = [c.strip() for c in os.environ.get("KFI_GDS_CL_CODES", "01").split(",") if c.strip()]

BASE = "https://apis.data.go.kr/B552486"
ENDPOINTS = {
    "approval": [f"{BASE}/opnFsuplAprv/opnFsuplAprv01", f"{BASE}/opnFsuplAprv/opnFsuplAprv02", f"{BASE}/opnFsuplAprv/opnFsuplAprv03"],
    "cancel": [f"{BASE}/opnFsuplRtrcn/opnFsuplRtrcn01", f"{BASE}/opnFsuplRtrcn/opnFsuplRtrcn02", f"{BASE}/opnFsuplRtrcn/opnFsuplRtrcn03"],
    "company": [f"{BASE}/opnApiMnfcCmpy/opnApiMnfcCmpy01"],
    "maint_by_unit": f"{BASE}/opnGcExsrImpmAply/opnGcExsrImpmAply02",
    "maint_by_no": f"{BASE}/opnGcExsrImpmAply/opnGcExsrImpmAply01",
}


def _normalize(s: str) -> str:
    return (s or "").replace(" ", "").replace("O", "0").replace("o", "0").upper()


def _normalize_name(s: str) -> str:
    return (s or "").replace(" ", "").replace("(주)", "").replace("주식회사", "").upper()


def _today_ymd() -> str:
    return date.today().strftime("%Y%m%d")


def _guess_type(endpoint: str) -> str:
    if endpoint.endswith("01"):
        return "형식승인"
    if endpoint.endswith("02"):
        return "성능인증"
    if endpoint.endswith("03"):
        return "KFI인정"
    return ""


def _call_api(url: str, params: dict) -> dict:
    if not SERVICE_KEY:
        raise RuntimeError("KFI_SERVICE_KEY가 설정되지 않았습니다. .env를 확인하세요.")
    q = {"ServiceKey": SERVICE_KEY, **params}
    res = requests.get(url, params=q, timeout=15)
    try:
        body = res.json()
    except ValueError:
        raise RuntimeError(f"KFI API 응답이 JSON이 아닙니다 (HTTP {res.status_code}): {res.text[:300]}")
    # 실제 응답(활용가이드 확인)은 {"data":[...], "header":{"resultCode":...}} 형태다.
    # 옛 data.go.kr 표준 포맷(response.header)이나 data.go.kr 공통 인증오류 포맷(cmmMsgHeader)도
    # 함께 대비한다 — 서비스키 미승인/오류 시 이쪽으로 응답이 오는 경우가 많다.
    header = body.get("header") or body.get("response", {}).get("header") or {}
    cmm = body.get("cmmMsgHeader")
    if cmm:
        raise RuntimeError(f"KFI API 인증/서비스 오류: {cmm.get('returnAuthMsg') or cmm.get('errMsg') or cmm}")
    result_code = header.get("resultCode", body.get("resultCode"))
    if result_code not in (None, "00", "0", 0):
        msg = header.get("resultMsg") or body.get("resultMsg") or result_code
        raise RuntimeError(f"KFI API 오류 응답: {msg}")
    if result_code is None and "data" not in body and "items" not in body and "item" not in body:
        # data도 없고 알려진 성공/오류 신호도 없는 낯선 응답 — 원인 파악을 위해 앞부분을 그대로 노출한다.
        raise RuntimeError(f"KFI API 예상치 못한 응답 형식: {str(body)[:300]}")
    return body


def _extract_rows(body: dict) -> list:
    # 공식 활용가이드(OpenAPI활용가이드_소방산업기술원_소방용품업체정보.docx) 확인 결과,
    # 이 기관(B552486) API의 실제 응답은 {"data": [...]} 형태다. 아래 나머지 분기는
    # (문서에 나온 필드표와 달리) 혹시 다른 세부기능이 다른 포맷을 쓸 경우를 대비한 폴백이다.
    if isinstance(body.get("data"), list):
        return body["data"]
    if isinstance(body.get("items"), list):
        return body["items"]
    items = body.get("response", {}).get("body", {}).get("items", {})
    if isinstance(items, dict) and isinstance(items.get("item"), list):
        return items["item"]
    if isinstance(body.get("body", {}).get("items"), list):
        return body["body"]["items"]
    if body.get("item"):
        return body["item"] if isinstance(body["item"], list) else [body["item"]]
    return []


def _extract_total(body: dict, fallback: int) -> int:
    header = body.get("header") or body.get("response", {}).get("header") or {}
    total = header.get("totalCount", body.get("totalCount", body.get("response", {}).get("body", {}).get("totalCount")))
    return fallback if total is None else int(total)


def _fetch_all_pages(url: str, base_params: dict, num_of_rows=100, max_pages=50) -> list:
    items = []
    for page_no in range(1, max_pages + 1):
        body = _call_api(url, {**base_params, "pageNo": page_no, "numOfRows": num_of_rows})
        rows = _extract_rows(body)
        items.extend(rows)
        total = _extract_total(body, len(items))
        # 실제 응답에는 totalCount가 없을 수도 있어(활용가이드 예제 참고), 이 경우 total은 fallback=len(items)이
        # 되어 아래 두 번째 조건으로는 판단이 안 된다. 그래서 "이번 페이지가 요청한 개수보다 적게 왔다"는
        # 것도 마지막 페이지 신호로 함께 본다.
        if not rows or len(rows) < num_of_rows or len(items) >= total:
            break
    return items


# ============ 동기화(Sync): 승인정보 / 취소정보 / 업체정보 -> 로컬 캐시 ============

def sync_approvals(from_aprv="20020101", to_aprv=None, gds_cl_codes=None) -> dict:
    to_aprv = to_aprv or _today_ymd()
    gds_cl_codes = gds_cl_codes or GDS_CL_CODES
    conn = db_module.get_conn()
    synced, errors = 0, []
    for endpoint in ENDPOINTS["approval"]:
        for code in gds_cl_codes:
            try:
                rows = _fetch_all_pages(endpoint, {"fromAprv": from_aprv, "toAprv": to_aprv, "gdsClCd": code})
            except Exception as e:
                errors.append(f"{endpoint}?gdsClCd={code}: {e}")
                continue
            for r in rows:
                number = r.get("ctfcnNo") or r.get("aprvNo")
                if not number:
                    continue
                conn.execute(
                    """INSERT INTO approval_cache (number,type,item,company,approved_date) VALUES (?,?,?,?,?)
                       ON CONFLICT(number) DO UPDATE SET type=excluded.type, item=excluded.item,
                         company=excluded.company, approved_date=excluded.approved_date""",
                    (number, _guess_type(endpoint), r.get("gdsNm") or r.get("ctfcnFomNm") or "",
                     r.get("cmpyNm") or "", str(r.get("aprvYmd") or r.get("ctfcnYmd") or "")),
                )
                synced += 1
    conn.commit()
    return {"synced": synced, "errors": errors}


def sync_cancellations(from_aprv="20020101", to_aprv=None, gds_cl_codes=None) -> dict:
    to_aprv = to_aprv or _today_ymd()
    gds_cl_codes = gds_cl_codes or GDS_CL_CODES
    conn = db_module.get_conn()
    synced, errors = 0, []
    for endpoint in ENDPOINTS["cancel"]:
        for code in gds_cl_codes:
            try:
                rows = _fetch_all_pages(endpoint, {"fromAprv": from_aprv, "toAprv": to_aprv, "gdsClCd": code})
            except Exception as e:
                errors.append(f"{endpoint}?gdsClCd={code}: {e}")
                continue
            for r in rows:
                number = r.get("ctfcnNo")
                if not number:
                    continue
                exists = conn.execute("SELECT number FROM approval_cache WHERE number=?", (number,)).fetchone()
                if not exists:
                    conn.execute(
                        "INSERT OR IGNORE INTO approval_cache (number,type,item,company,approved_date) VALUES (?,?,?,?,?)",
                        (number, _guess_type(endpoint), r.get("ctfcnFomNm") or "", r.get("cmpyNm") or "", ""),
                    )
                conn.execute(
                    "UPDATE approval_cache SET cancelled=1, cancel_date=?, cancel_reason=? WHERE number=?",
                    (r.get("rtrcnYmd") or "", r.get("dspsCn") or "", number),
                )
                synced += 1
    conn.commit()
    return {"synced": synced, "errors": errors}


def sync_companies(gds_cl_codes=None) -> dict:
    gds_cl_codes = gds_cl_codes or GDS_CL_CODES
    conn = db_module.get_conn()
    synced, errors = 0, []
    for endpoint in ENDPOINTS["company"]:
        for code in gds_cl_codes:
            try:
                rows = _fetch_all_pages(endpoint, {"gdsClCd": code})
            except Exception as e:
                errors.append(f"{endpoint}?gdsClCd={code}: {e}")
                continue
            for r in rows:
                name = r.get("cmpyNm")
                if not name:
                    continue
                conn.execute(
                    """INSERT INTO companies (name,role,rep,address,phone) VALUES (?,?,?,?,?)
                       ON CONFLICT(name) DO UPDATE SET rep=excluded.rep, address=excluded.address, phone=excluded.phone""",
                    (name, "제조업체", r.get("rprsvPnm") or r.get("rprsvNm") or r.get("ceo") or "", r.get("fctryAdr") or r.get("adres") or r.get("address") or "", r.get("fctryTelno") or r.get("telno") or r.get("tel") or ""),
                )
                synced += 1
    conn.commit()
    return {"synced": synced, "errors": errors}


def sync_all(from_aprv=None, to_aprv=None, gds_cl_codes=None) -> dict:
    kwargs = {}
    if from_aprv:
        kwargs["from_aprv"] = from_aprv
    if to_aprv:
        kwargs["to_aprv"] = to_aprv
    if gds_cl_codes:
        kwargs["gds_cl_codes"] = gds_cl_codes
    return {
        "approvals": sync_approvals(**kwargs),
        "cancellations": sync_cancellations(**kwargs),
        "companies": sync_companies(gds_cl_codes=gds_cl_codes or GDS_CL_CODES),
    }


# ============ 실시간 조회: 정비이력(합격표시번호) ============

def fetch_maintenance_by_unit(psmrk_prfc_no: str) -> list:
    body = _call_api(ENDPOINTS["maint_by_unit"], {"psmrkPrfcNo": psmrk_prfc_no, "pageNo": 1, "numOfRows": 50})
    return [
        {
            "company": r.get("exsrImpmCmpyNm") or "",
            "date": str(r.get("exsrImpmYmd") or ""),
            "amount": r.get("exagQtyCn") or "",
            "maintNo": r.get("exsrImpmYrNo") or "",
        }
        for r in _extract_rows(body)
    ]


# ============ 앱이 실제로 쓰는 조회 함수 (mock/real 공통: 항상 로컬 캐시 기반) ============

def get_approval(number: str) -> dict:
    conn = db_module.get_conn()
    row = conn.execute("SELECT * FROM approval_cache WHERE number=?", (number,)).fetchone()
    if not row:
        return {"status": "unregistered"}
    if row["cancelled"]:
        return {
            "status": "cancelled",
            "key": row["number"],
            "data": {"type": row["type"], "item": row["item"], "company": row["company"], "approvedDate": row["approved_date"]},
            "cancel": {"cancelDate": row["cancel_date"], "reason": row["cancel_reason"]},
        }
    return {
        "status": "valid",
        "key": row["number"],
        "data": {"type": row["type"], "item": row["item"], "company": row["company"], "approvedDate": row["approved_date"]},
    }


def find_approval_loose(number: str) -> dict | None:
    """정확히 일치하는 승인번호가 없을 때(챗봇처럼 표기가 살짝 다를 수 있는 입력),
    공백/대소문자 차이를 무시하고 한 번 더 시도한다. (get_approval은 정확 일치만 봄)"""
    conn = db_module.get_conn()
    target = _normalize(number)
    if not target:
        return None
    rows = conn.execute("SELECT * FROM approval_cache").fetchall()
    for row in rows:
        if _normalize(row["number"]) != target:
            continue
        if row["cancelled"]:
            return {
                "status": "cancelled",
                "key": row["number"],
                "data": {"type": row["type"], "item": row["item"], "company": row["company"], "approvedDate": row["approved_date"]},
                "cancel": {"cancelDate": row["cancel_date"], "reason": row["cancel_reason"]},
            }
        return {
            "status": "valid",
            "key": row["number"],
            "data": {"type": row["type"], "item": row["item"], "company": row["company"], "approvedDate": row["approved_date"]},
        }
    return None


def mark_approval_cancelled(number: str, reason: str):
    conn = db_module.get_conn()
    today = date.today().isoformat()
    conn.execute(
        "UPDATE approval_cache SET cancelled=1, cancel_date=?, cancel_reason=? WHERE number=?",
        (today, reason, number),
    )
    conn.commit()


def find_company(name: str):
    conn = db_module.get_conn()
    target = _normalize_name(name)
    if not target:
        return None
    rows = conn.execute("SELECT * FROM companies").fetchall()
    for c in rows:
        cn = _normalize_name(c["name"])
        if target in cn or cn in target:
            return dict(c)
    return None


def get_unit(code: str) -> dict | None:
    conn = db_module.get_conn()
    rows = conn.execute("SELECT * FROM units").fetchall()
    row = next((u for u in rows if _normalize(u["code"]) == _normalize(code)), None)
    if not row:
        return None

    maint = None
    if not USE_MOCK and SERVICE_KEY:
        try:
            maint = fetch_maintenance_by_unit(row["code"])
        except Exception:
            maint = None  # 실패 시 로컬 캐시로 폴백
    if maint is None:
        maint_rows = conn.execute(
            "SELECT * FROM maintenance_records WHERE unit_code=? ORDER BY date DESC", (row["code"],)
        ).fetchall()
        # 실시간 API 결과(camelCase)와 필드명을 맞춰 다운스트림에서 동일하게 다룰 수 있도록 정규화
        maint = [
            {"company": m["company"], "date": m["date"], "amount": m["amount"], "maintNo": m["maint_no"]}
            for m in maint_rows
        ]

    return {"code": row["code"], "item": row["item"], "firstApproved": row["first_approved"], "maker": row["maker"], "maintenance": maint}


def find_recall_by_item_text(item_text: str):
    conn = db_module.get_conn()
    rows = conn.execute("SELECT * FROM approval_cache WHERE cancelled=1").fetchall()
    for c in rows:
        if item_text in c["item"] or c["item"] in item_text:
            return dict(c)
    return None
