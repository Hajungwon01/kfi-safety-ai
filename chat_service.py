"""RAG 기반 상담 챗봇 서비스 (Node판 routes/chat.js 포팅).
설계 원칙: 승인번호 등록여부/내용연수 계산 같은 "사실 판정"은 절대 LLM에 맡기지 않는다.
(1) 지식베이스 검색 + (2) 사용자가 방금 조회한 승인번호/유닛의 "실제 DB 조회 결과"를
컨텍스트로 모아 LLM에게 "설명"만 맡긴다. LLM이 사실관계를 새로 판단하지 않도록 프롬프트로 강제한다."""
import json

import rag
import llm_client as llm
import kfi_client as kfi
import chat_tools
from lifecycle import evaluate_unit


def build_session_context(context: dict | None) -> str:
    if not context:
        return ""
    parts = []
    approval_number = context.get("approvalNumber")
    if approval_number:
        try:
            r = kfi.get_approval(approval_number)
            parts.append(f"[사용자가 방금 조회한 승인번호: {approval_number}]\n{json.dumps(r, ensure_ascii=False)}")
        except Exception:
            pass
    unit_code = context.get("unitCode")
    if unit_code:
        unit = kfi.get_unit(unit_code)
        if unit:
            recall = kfi.find_recall_by_item_text(unit["item"])
            ev = evaluate_unit(
                {"firstApproved": unit["firstApproved"], "maintenance": [{"date": m["date"]} for m in unit["maintenance"]]},
                {"item": recall["item"], "reason": recall["cancel_reason"]} if recall else None,
            )
            payload = {"unit": {"item": unit["item"], "maker": unit["maker"]}, **ev}
            parts.append(f"[사용자가 방금 조회한 소화기: {unit_code}]\n{json.dumps(payload, ensure_ascii=False)}")
    return "\n\n".join(parts)


def answer_chat(message: str, context: dict | None = None, user: dict | None = None) -> dict:
    """반환 형태:
    - tool:           {mode, tool, answer, result, sources:[{id,title}]}   (채팅으로 1부/2부 기능 직접 실행됨)
    - retrieval-only: {mode, note, sources:[{id,title,text}], sessionContext}
    - llm:            {mode, answer, sources:[{id,title}]}
    - error:          {error, sources:[{id,title}]}  (호출측에서 502 취급)

    메시지 안에 승인번호/합격표시번호/업체명/공문 텍스트로 보이는 패턴이 있으면 chat_tools가
    실제 kfi_client/unit_service/doc_analyzer를 직접 호출해 "사실"을 확정한다. LLM은 이 사실을
    설명만 할 뿐 스스로 판단하지 않는다(OPENAI_API_KEY가 없어도 tool 결과는 그대로 답변됨).
    """
    if not message or not message.strip():
        return {"error": "message가 필요합니다."}

    tool_call = chat_tools.detect_and_run(message, user)
    retrieved = rag.search(message, 4)
    session_context = build_session_context(context)
    if tool_call:
        tool_block = chat_tools.tool_result_as_context_block(tool_call)
        session_context = f"{session_context}\n\n{tool_block}" if session_context else tool_block

    if not llm.has_key():
        if tool_call:
            return {
                "mode": "tool",
                "tool": tool_call["tool"],
                "args": tool_call["args"],
                "answer": chat_tools.format_tool_answer(tool_call),
                "result": tool_call["result"],
                "sources": [{"id": r["id"], "title": r["title"]} for r in retrieved[:2]],
            }
        return {
            "mode": "retrieval-only",
            "note": "OPENAI_API_KEY가 설정되지 않아 자연어 답변 대신, 관련도가 높은 참고자료를 그대로 보여드립니다.",
            "sources": [{"id": r["id"], "title": r["title"], "text": r["text"]} for r in retrieved],
            "sessionContext": session_context or None,
        }

    kb_text = "\n\n".join(f"### {r['title']} (출처: {r['source']})\n{r['text']}" for r in retrieved)
    system_prompt = "\n".join([
        "당신은 'KFI 소방용품 안전지킴이 AI'의 상담 챗봇입니다.",
        "반드시 아래 [참고자료]와 [현재 조회 결과]만 근거로 답하세요.",
        "참고자료에 없는 내용은 추측하지 말고 '확인이 필요합니다'라고 답하세요.",
        "특히 특정 제품이 정품인지, 리콜 대상인지, 내용연수가 지났는지, 업체가 등록업체인지 같은 사실 판정은",
        "반드시 [현재 조회 결과]를 그대로 따르고, 스스로 새로 판단하지 마세요. [현재 조회 결과]에 방금 조회된",
        "내용이 있다면 그것이 사용자 질문에 대한 답일 가능성이 높으니 적극적으로 활용해서 답하세요.",
        "답변은 한국어로, 간결하고 친절하게 작성하세요.",
        "",
        "[참고자료]",
        kb_text or "(관련 참고자료를 찾지 못했습니다)",
        "",
        "[현재 조회 결과]",
        session_context or "(사용자가 아직 조회한 항목이 없습니다)",
    ])

    try:
        answer = llm.chat([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ])
        mode = "tool" if tool_call else "llm"
        resp = {"mode": mode, "answer": answer, "sources": [{"id": r["id"], "title": r["title"]} for r in retrieved]}
        if tool_call:
            resp["tool"] = tool_call["tool"]
            resp["args"] = tool_call["args"]
            resp["result"] = tool_call["result"]
        return resp
    except Exception as e:
        if tool_call:
            # LLM 설명은 실패했지만, 사실 조회 자체(tool_call)는 이미 성공했으니 그 결과는 그대로 보여준다.
            return {
                "mode": "tool",
                "tool": tool_call["tool"],
                "args": tool_call["args"],
                "answer": chat_tools.format_tool_answer(tool_call),
                "result": tool_call["result"],
                "sources": [{"id": r["id"], "title": r["title"]} for r in retrieved[:2]],
            }
        return {"error": f"LLM 호출 실패: {e}", "sources": [{"id": r["id"], "title": r["title"]} for r in retrieved]}
