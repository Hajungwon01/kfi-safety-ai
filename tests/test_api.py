"""FastAPI TestClient 기반 API 통합 테스트 (Node판 test/run.js와 동일한 시나리오를 검증)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["DB_PATH"] = ":memory:"
os.environ["USE_MOCK"] = "true"
os.environ["JWT_SECRET"] = "test-secret-api"

import db as db_module
db_module.reset_conn()

from fastapi.testclient import TestClient
import main

client = TestClient(main.app)


def setup_function():
    db_module.reset_conn()


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def admin_header():
    r = client.post("/api/auth/login", json={"email": db_module.ADMIN_EMAIL, "password": db_module.ADMIN_PASSWORD})
    assert r.status_code == 200
    return auth_header(r.json()["token"])


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["mockMode"] is True


def test_register_and_login():
    r = client.post("/api/auth/register", json={"email": "u1@example.com", "password": "pw1234"})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == "u1@example.com"
    assert body["token"]

    r2 = client.post("/api/auth/login", json={"email": "u1@example.com", "password": "pw1234"})
    assert r2.status_code == 200

    r3 = client.post("/api/auth/login", json={"email": "u1@example.com", "password": "wrong"})
    assert r3.status_code == 400


def test_duplicate_register_rejected():
    client.post("/api/auth/register", json={"email": "dup@example.com", "password": "pw1234"})
    r = client.post("/api/auth/register", json={"email": "dup@example.com", "password": "pw1234"})
    assert r.status_code == 400


def test_analyze_doc_high_risk():
    r = client.post("/api/approvals/analyze-doc", json={"text": "즉시 비치하지 않으면 과태료가 부과됩니다. 오늘까지 계좌로 입금 바랍니다."})
    assert r.status_code == 200
    assert r.json()["level"] in ("고위험", "중위험")


def test_analyze_doc_empty_text_400():
    r = client.post("/api/approvals/analyze-doc", json={"text": "  "})
    assert r.status_code == 400


def test_approval_lookup_valid_cancelled_unregistered():
    r = client.get("/api/approvals/" + "형식승인 제2022-3-045호")
    assert r.json()["status"] == "valid"

    r2 = client.get("/api/approvals/" + "형식승인 제2099-9-999호")
    assert r2.json()["status"] == "unregistered"


def test_company_lookup():
    r = client.get("/api/companies/" + "한국소방기기")
    assert r.json()["status"] == "registered"
    r2 = client.get("/api/companies/" + "가짜소방유통")
    assert r2.json()["status"] == "unregistered"


def test_unit_requires_auth_for_register():
    r = client.post("/api/units/EYTN-52981/register")
    assert r.status_code == 401


def test_full_flow_register_unit_and_locker():
    reg = client.post("/api/auth/register", json={"email": "locker@example.com", "password": "pw1234"}).json()
    token = reg["token"]

    r = client.get("/api/units/EYTN-52981")
    assert r.json()["found"] is True

    r2 = client.post("/api/units/EYTN-52981/register", headers=auth_header(token))
    assert r2.status_code == 201

    r3 = client.get("/api/units/mine", headers=auth_header(token))
    assert len(r3.json()) == 1
    assert r3.json()[0]["unit"]["code"] == "EYTN-52981"


def test_report_and_stats():
    r = client.post("/api/reports", json={"type": "fraud", "region": "서울특별시", "target": "x", "reason": "y", "riskLevel": "위험"})
    assert r.status_code == 201
    stats = client.get("/api/reports/stats", headers=admin_header()).json()
    assert stats["fraud"] == 1


def test_reports_stats_and_list_require_admin():
    r = client.get("/api/reports/stats")
    assert r.status_code == 401  # 로그인 자체가 안 된 경우

    reg = client.post("/api/auth/register", json={"email": "notadmin@example.com", "password": "pw1234"}).json()
    r2 = client.get("/api/reports/stats", headers=auth_header(reg["token"]))
    assert r2.status_code == 403  # 일반 사용자는 접근 불가

    r3 = client.get("/api/reports", headers=admin_header())
    assert r3.status_code == 200


def test_admin_sample_data_requires_admin_and_returns_cached_rows():
    r = client.get("/api/admin/sample-data")
    assert r.status_code == 401

    reg = client.post("/api/auth/register", json={"email": "notadmin2@example.com", "password": "pw1234"}).json()
    r2 = client.get("/api/admin/sample-data", headers=auth_header(reg["token"]))
    assert r2.status_code == 403

    r3 = client.get("/api/admin/sample-data", headers=admin_header())
    assert r3.status_code == 200
    body = r3.json()
    assert "validApprovals" in body and "companies" in body and "units" in body
    assert body["counts"]["approval_cache"] >= len(body["validApprovals"])


def test_register_cannot_self_grant_admin_role():
    reg = client.post("/api/auth/register", json={"email": "tryadmin@example.com", "password": "pw1234", "role": "admin"}).json()
    assert reg["user"]["role"] == "facility_manager"
    r = client.post("/api/admin/simulate-recall", json={}, headers=auth_header(reg["token"]))
    assert r.status_code == 403


def test_full_recall_scenario():
    reg = client.post("/api/auth/register", json={"email": "recall@example.com", "password": "pw1234"}).json()
    token = reg["token"]
    client.post("/api/units/EYTN-52981/register", headers=auth_header(token))

    r = client.post("/api/admin/simulate-recall", json={}, headers=admin_header())
    assert r.status_code == 200
    body = r.json()
    assert body["notified"] == 1

    r2 = client.post("/api/admin/simulate-recall", json={}, headers=admin_header())
    assert r2.status_code == 409  # 중복 트리거 방지

    locker = client.get("/api/units/mine", headers=auth_header(token)).json()
    assert locker[0]["grade"] == "위험(리콜대상)"

    notifs = client.get("/api/notifications/mine", headers=auth_header(token)).json()
    assert len(notifs) == 1
    assert "리콜" in notifs[0]["message"]

    approval = client.get("/api/approvals/" + "성능인증 제2023-7-118호").json()
    assert approval["status"] == "cancelled"


def test_chat_retrieval_only_without_openai_key():
    os.environ.pop("OPENAI_API_KEY", None)
    import llm_client
    llm_client.API_KEY = ""
    r = client.post("/api/chat", json={"message": "소화기 내용연수 지나면 어떻게 되나요?"})
    assert r.status_code == 200
    assert r.json()["mode"] == "retrieval-only"


def test_chat_performs_part1_lookup_via_api():
    """/api/chat에 승인번호를 그냥 문장으로 보내면, 실제 1부 조회 로직이 실행돼야 한다."""
    r = client.post("/api/chat", json={"message": "형식승인 제2022-3-045호 이거 진짜예요?"})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "tool"
    assert body["tool"] == "check_approval"
    assert body["result"]["status"] == "valid"


def test_chat_performs_part2_lookup_and_registers_unit_when_authenticated():
    """로그인한 상태로 채팅에 합격표시번호를 보내면 2부처럼 내 소화기함에 자동 등록돼야 한다."""
    reg = client.post("/api/auth/register", json={"email": "chatuser@example.com", "password": "pw1234"}).json()
    token = reg["token"]

    r = client.post("/api/chat", json={"message": "BQKD-88213 조회해줘"}, headers=auth_header(token))
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "tool"
    assert body["tool"] == "check_unit"
    assert body["result"]["registeredNow"] is True

    mine = client.get("/api/units/mine", headers=auth_header(token)).json()
    assert any(u["unit"]["code"] == "BQKD-88213" for u in mine)


def test_chat_unit_lookup_without_auth_does_not_register():
    r = client.post("/api/chat", json={"message": "CPLM-30044 조회해줘"})
    assert r.status_code == 200
    body = r.json()
    assert body["tool"] == "check_unit"
    assert "registeredNow" not in body["result"]


def test_chat_response_includes_args_for_report_targets():
    """채팅 응답에 args가 포함돼야, 프론트가 신고 대상(승인번호/업체명)을 알 수 있다."""
    r = client.post("/api/chat", json={"message": "형식승인 제9999-9-999호 확인해줘"})
    body = r.json()
    assert body["tool"] == "check_approval"
    assert body["args"]["number"] == "형식승인 제9999-9-999호"


def test_chat_lists_notifications_via_api():
    reg = client.post("/api/auth/register", json={"email": "chatnotif@example.com", "password": "pw1234"}).json()
    token = reg["token"]
    r = client.post("/api/chat", json={"message": "내 알림 확인"}, headers=auth_header(token))
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "tool"
    assert body["tool"] == "list_notifications"
    assert body["result"]["items"] == []


def test_chat_lists_units_via_api():
    reg = client.post("/api/auth/register", json={"email": "chatunits@example.com", "password": "pw1234"}).json()
    token = reg["token"]
    client.post("/api/chat", json={"message": "EYTN-52981 조회해줘"}, headers=auth_header(token))
    r = client.post("/api/chat", json={"message": "내 소화기함 보여줘"}, headers=auth_header(token))
    assert r.status_code == 200
    body = r.json()
    assert body["tool"] == "list_units"
    assert any(u["unit"]["code"] == "EYTN-52981" for u in body["result"]["items"])


def test_chat_empty_message_400():
    r = client.post("/api/chat", json={"message": ""})
    assert r.status_code == 400
