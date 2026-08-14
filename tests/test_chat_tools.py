"""챗봇이 메시지에서 1부/2부 조회 의도를 감지해 실제 백엔드 로직을 직접 호출하는지 검증."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["DB_PATH"] = ":memory:"
os.environ["USE_MOCK"] = "true"

import db as db_module
db_module.reset_conn()

import chat_tools


def test_detects_approval_number_and_looks_it_up():
    r = chat_tools.detect_and_run("형식승인 제2022-3-045호 이거 진짜예요?")
    assert r is not None
    assert r["tool"] == "check_approval"
    assert r["result"]["status"] == "valid"
    assert "정상 등록" in chat_tools.format_tool_answer(r)


def test_detects_unregistered_approval_number():
    r = chat_tools.detect_and_run("형식승인 제9999-9-999호 확인해줘")
    assert r["tool"] == "check_approval"
    assert r["result"]["status"] == "unregistered"
    assert "🚨" in chat_tools.format_tool_answer(r)


def test_detects_real_kfi_style_approval_number_without_type_prefix():
    """실 KFI 데이터의 승인/인정번호는 mock처럼 '형식승인 제0000-0-000호' 형태가 아니라
    '리소26-9'처럼 유형 접두어 없는 raw 번호로 저장된다. 이 형식도 감지돼야 한다."""
    number = "리소26-9"
    db_module.get_conn().execute(
        "INSERT INTO approval_cache (number,type,item,company,approved_date) VALUES (?,?,?,?,?)",
        (number, "KFI인정", "소화기의 소형리튬이온전지화재 소화성능", "주식회사 동아화이어", "2026-08-10"),
    )
    db_module.get_conn().commit()

    r = chat_tools.detect_and_run(f"{number} 진짜예요?")
    assert r is not None
    assert r["tool"] == "check_approval"
    assert r["args"]["number"] == number
    assert r["result"]["status"] == "valid"


def test_detects_company_with_hint_word():
    r = chat_tools.detect_and_run("대한안전산업(주)에서 사려는데 등록된 업체 맞나요?")
    assert r["tool"] == "check_company"
    assert r["result"]["status"] == "registered"


def test_ignores_company_name_without_hint_word():
    # "업체/회사/판매자/판매처" 같은 단서 단어가 없으면 회사명처럼 보여도 의도로 보지 않는다(오탐 방지)
    r = chat_tools.detect_and_run("대한안전산업(주) 홈페이지 주소 좀 알려줘")
    assert r is None or r["tool"] != "check_company"


def test_detects_unit_code_and_looks_it_up():
    r = chat_tools.detect_and_run("AXZG-45271 이거 조회해줘")
    assert r["tool"] == "check_unit"
    assert r["result"]["found"] is True
    assert r["result"]["unit"]["code"] == "AXZG-45271"


def test_unit_lookup_auto_registers_when_logged_in():
    user = {"id": 999}
    r = chat_tools.detect_and_run("BQKD-88213 조회해줘", user=user)
    assert r["tool"] == "check_unit"
    assert r["result"]["registeredNow"] is True
    from services import unit_service
    mine = unit_service.list_mine(999)
    assert any(u["unit"]["code"] == "BQKD-88213" for u in mine)


def test_unit_lookup_does_not_register_when_anonymous():
    r = chat_tools.detect_and_run("CPLM-30044 조회해줘")
    assert r["tool"] == "check_unit"
    assert "registeredNow" not in r["result"]


def test_detects_scam_looking_document_text():
    text = "리튬이온 전용 소화기를 즉시 비치하지 않으면 과태료가 부과됩니다. 오늘까지 계좌로 입금 바랍니다."
    r = chat_tools.detect_and_run(text)
    assert r["tool"] == "analyze_doc"
    assert r["result"]["level"] == "고위험"


def test_faq_question_is_not_treated_as_document_analysis():
    r = chat_tools.detect_and_run("소화기 내용연수 지나면 어떻게 되나요?")
    assert r is None


def test_plain_greeting_has_no_tool():
    assert chat_tools.detect_and_run("안녕하세요") is None


def test_empty_message_has_no_tool():
    assert chat_tools.detect_and_run("") is None
    assert chat_tools.detect_and_run(None) is None


def test_list_notifications_intent_requires_login():
    assert chat_tools.detect_and_run("내 알림 확인") is None  # 비로그인 시 감지 안 함


def test_list_notifications_intent_detected_when_logged_in():
    user = {"id": 5001}
    for msg in ["내 알림 확인", "알림 보여줘", "알림"]:
        r = chat_tools.detect_and_run(msg, user)
        assert r is not None and r["tool"] == "list_notifications"
        assert "아직 쌓인 알림이 없습니다" in chat_tools.format_tool_answer(r)


def test_faq_question_about_notifications_is_not_treated_as_list_command():
    # "알림은 어떻게 오나요?"처럼 질문형이면 목록 조회 의도로 보지 않는다(오탐 방지)
    r = chat_tools.detect_and_run("리콜 발생하면 알림은 어떻게 확인하나요?", {"id": 5002})
    assert r is None or r["tool"] != "list_notifications"


def test_list_units_intent_detected_and_reflects_registered_units():
    user = {"id": 5003}
    chat_tools.detect_and_run("EYTN-52981 조회해줘", user)  # 먼저 하나 등록
    r = chat_tools.detect_and_run("내 소화기함 보여줘", user)
    assert r is not None and r["tool"] == "list_units"
    assert any(u["unit"]["code"] == "EYTN-52981" for u in r["result"]["items"])
    assert "EYTN-52981" in chat_tools.format_tool_answer(r)


def test_list_units_intent_requires_login():
    assert chat_tools.detect_and_run("내 소화기함 보여줘") is None


def test_unedited_unit_preset_template_gets_placeholder_hint_not_llm_fallback():
    """프리셋이 채워준 '합격표시번호 조회해줘'를 그대로 보내면(빈칸을 안 채우면),
    LLM에게 넘어가 엉뚱한 답을 하지 않고 실제 값을 채우거나 사진을 올리라고 바로 안내해야 한다."""
    r = chat_tools.detect_and_run("합격표시번호 조회해줘", {"id": 1})
    assert r is not None and r["tool"] == "placeholder_hint"
    answer = chat_tools.format_tool_answer(r)
    assert "AXZG-45271" in answer or "실제 번호" in answer
    assert "📷" in answer


def test_unedited_company_preset_template_gets_placeholder_hint():
    r = chat_tools.detect_and_run("업체명 등록된 업체 맞나요?")
    assert r is not None and r["tool"] == "placeholder_hint"
    assert "업체명" in chat_tools.format_tool_answer(r)


def test_unedited_doc_preset_template_gets_placeholder_hint():
    r = chat_tools.detect_and_run("여기에 공문·안내문 내용을 붙여넣으세요")
    assert r is not None and r["tool"] == "placeholder_hint"
    assert "📷" in chat_tools.format_tool_answer(r)


def test_real_unit_code_after_preset_still_works_normally():
    """빈칸을 실제 값으로 채운 경우엔 placeholder_hint가 아니라 정상적으로 조회돼야 한다."""
    r = chat_tools.detect_and_run("AXZG-45271 조회해줘")
    assert r["tool"] == "check_unit"


def test_genuine_faq_question_about_unit_code_is_not_treated_as_placeholder():
    """'합격표시번호가 뭐예요?' 같은 진짜 질문은 placeholder_hint로 가로채지 않고 기존 RAG/LLM 흐름에 맡긴다."""
    r = chat_tools.detect_and_run("합격표시번호가 뭐예요?")
    assert r is None
