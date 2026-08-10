import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["DB_PATH"] = ":memory:"
os.environ["USE_MOCK"] = "true"
os.environ.pop("OPENAI_API_KEY", None)

import db as db_module
db_module.reset_conn()

import rag
import llm_client as llm
import chat_service


def test_lexical_search_finds_content_year_section():
    results = rag.lexical_search("내용연수 지나면 어떻게 되나요")
    assert len(results) > 0
    assert any("내용연수" in r["text"] for r in results)


def test_chunks_loaded_from_kb():
    assert len(rag.CHUNKS) > 0


def test_chat_retrieval_only_without_key():
    llm.API_KEY = ""  # 키 없음 상태 명시
    r = chat_service.answer_chat("소화기 내용연수 지나면 어떻게 되나요?")
    assert r["mode"] == "retrieval-only"
    assert len(r["sources"]) > 0


def test_chat_empty_message_errors():
    r = chat_service.answer_chat("")
    assert "error" in r


def test_chat_session_context_included(monkeypatch):
    import kfi_client as kfi
    approval = kfi.get_approval("형식승인 제2022-3-045호")
    assert approval["status"] == "valid"
    ctx = chat_service.build_session_context({"approvalNumber": "형식승인 제2022-3-045호"})
    assert "형식승인 제2022-3-045호" in ctx
    assert "valid" in ctx


def test_chat_llm_mode_stubbed(monkeypatch):
    llm.API_KEY = "fake-key-for-test"
    captured = {}

    def fake_chat(messages, model=None, temperature=0.2):
        captured["messages"] = messages
        return "스텁 답변입니다."

    monkeypatch.setattr(llm, "chat", fake_chat)
    r = chat_service.answer_chat("이거 정품이에요?", {"approvalNumber": "형식승인 제2022-3-045호"})
    assert r["mode"] == "llm"
    assert r["answer"] == "스텁 답변입니다."
    system_msg = captured["messages"][0]["content"]
    assert "참고자료" in system_msg
    assert "형식승인 제2022-3-045호" in system_msg
    llm.API_KEY = ""


def test_chat_llm_failure_returns_error(monkeypatch):
    llm.API_KEY = "fake-key-for-test"

    def failing_chat(messages, model=None, temperature=0.2):
        raise RuntimeError("network down")

    monkeypatch.setattr(llm, "chat", failing_chat)
    r = chat_service.answer_chat("질문")
    assert "error" in r
    llm.API_KEY = ""


def test_chat_tool_mode_without_llm_key_answers_directly():
    """OPENAI_API_KEY가 없어도, 메시지에 승인번호가 있으면 챗봇이 1부 기능을 그대로 수행해야 한다."""
    llm.API_KEY = ""
    r = chat_service.answer_chat("형식승인 제2022-3-045호 진짜예요?")
    assert r["mode"] == "tool"
    assert r["tool"] == "check_approval"
    assert r["result"]["status"] == "valid"
    assert "정상 등록" in r["answer"]


def test_chat_tool_mode_registers_unit_when_logged_in():
    llm.API_KEY = ""
    user = {"id": 12345}
    r = chat_service.answer_chat("EYTN-52981 이거 조회해줘", user=user)
    assert r["mode"] == "tool"
    assert r["tool"] == "check_unit"
    assert r["result"]["registeredNow"] is True
    import kfi_client as kfi
    from services import unit_service
    assert any(u["unit"]["code"] == "EYTN-52981" for u in unit_service.list_mine(12345))


def test_chat_tool_result_is_fed_into_llm_prompt_not_hallucinated(monkeypatch):
    """LLM 키가 있어도 사실(조회 결과)은 chat_tools가 직접 조회한 값 그대로 프롬프트에 박히는지 확인."""
    llm.API_KEY = "fake-key-for-test"
    captured = {}

    def fake_chat(messages, model=None, temperature=0.2):
        captured["messages"] = messages
        return "스텁 답변: 정상 등록된 번호입니다."

    monkeypatch.setattr(llm, "chat", fake_chat)
    r = chat_service.answer_chat("성능인증 제2023-7-118호 이거 살펴봐줘")
    assert r["mode"] == "tool"
    assert r["tool"] == "check_approval"
    system_msg = captured["messages"][0]["content"]
    assert "성능인증 제2023-7-118호" in system_msg
    assert "valid" in system_msg
    llm.API_KEY = ""


def test_chat_tool_falls_back_to_deterministic_answer_when_llm_fails(monkeypatch):
    """LLM 설명이 실패해도, 이미 확정된 조회 결과(tool_call)는 그대로 답변돼야 한다(사실 확인은 LLM에 의존하지 않음)."""
    llm.API_KEY = "fake-key-for-test"

    def failing_chat(messages, model=None, temperature=0.2):
        raise RuntimeError("network down")

    monkeypatch.setattr(llm, "chat", failing_chat)
    r = chat_service.answer_chat("형식승인 제2022-3-045호 진짜예요?")
    assert r["mode"] == "tool"
    assert r["result"]["status"] == "valid"
    assert "error" not in r
    llm.API_KEY = ""
