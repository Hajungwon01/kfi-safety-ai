"""챗봇이 자연어 메시지에서 1부/2부 조회 의도를 감지해, 실제 결정론적 백엔드 로직을
직접 호출하는 도구모음.

설계 원칙(chat_service.py와 동일): 승인번호 등록여부/내용연수 계산/리콜 여부 같은 "사실 판정"은
절대 LLM이 새로 판단하지 않는다. 여기서 감지→실행까지 전부 정규식 + DB 조회로만 이뤄지고,
LLM은(설정돼 있다면) 이 결과를 "설명"하는 역할만 한다. OPENAI_API_KEY가 없어도
format_tool_answer()가 결과를 바로 한국어 문장으로 만들어주므로 챗봇이 항상 1부/2부 기능을
그대로 수행할 수 있다.
"""
import re

import kfi_client as kfi
from doc_analyzer import analyze_document
from services import unit_service, notification_service

APPROVAL_TYPE_RE = re.compile(r"(형식승인|성능인증|KFI\s*인정)")
# 예전 mock 데이터 표기(예: "형식승인 제2022-3-045호")용 패턴. 실 KFI 데이터는 이 형식을 쓰지 않는다.
APPROVAL_NUM_RE = re.compile(r"제\s?\d{4}\s?[-–]\s?\d{1,2}\s?[-–]\s?\d{2,4}\s?호")
# 실 KFI 데이터의 승인/인정번호 표기(예: "리소26-9", "가스25-123")용 패턴 — 한글 접두어 + 연도(2자리)
# + 붙임표 + 일련번호. UNIT_CODE_RE(로마자 접두어)와 겹치지 않도록 한글 접두어만 매칭한다.
APPROVAL_NUM_RE_REAL = re.compile(r"\b[가-힣]{1,4}\d{2}[-–]\d{1,4}\b")
UNIT_CODE_RE = re.compile(r"\b[A-Za-z]{3,5}[\s-]?\d{4,6}\b")
COMPANY_HINT_RE = re.compile(r"(업체|회사|판매자|판매처)")
COMPANY_NAME_RE = re.compile(r"[가-힣A-Za-z0-9&·]+(?:\(주\)|주식회사[가-힣A-Za-z0-9&·]*)")
QUESTION_ENDING_RE = re.compile(r"(요|까요|나요|습니까|가요|죠)\s*\?\s*$")
DOC_KEYWORDS = ["소화기", "비치", "과태료", "입금", "계좌", "소방서", "공문", "안내문", "즉시", "법령", "제출"]
# "알림은 언제 오나요?" 같은 FAQ 질문과 구분하기 위해 명령형 표현일 때만 반응한다.
NOTIF_IMPERATIVE_RE = re.compile(r"^(내\s*)?알림\s*(확인|보여줘|조회|목록)?\s*[.!]?$")
NOTIF_REQUEST_RE = re.compile(r"알림.*(보여줘|확인해줘|알려줘)")
LOCKER_IMPERATIVE_RE = re.compile(r"^(내\s*)?소화기함\s*(확인|보여줘|조회|목록)?\s*[.!]?$")
LOCKER_REQUEST_RE = re.compile(r"소화기함.*(보여줘|확인해줘|알려줘)")

# 프리셋 칩이 채팅 입력창에 채워주는 빈칸(예: "합격표시번호 조회해줘")을 사용자가 채우지 않고
# 그대로 보내면, 위 감지 로직들은 아무것도 못 찾아 LLM에게 넘어가 버린다. LLM은 실제 값이 없다는
# 걸 모르니 엉뚱하게 답할 수 있어, 이 "빈칸 미입력" 상태를 먼저 감지해 바로 안내한다.
PLACEHOLDER_HINTS = [
    (re.compile(r"^합격표시번호\s*조회해줘\s*[.!]?$"),
     "합격표시번호 자리가 채워지지 않았어요. 실제 번호(예: AXZG-45271)로 바꿔서 보내주시거나, 입력창 옆 📷 버튼으로 소화기 라벨 사진을 업로드해주세요."),
    (re.compile(r"^업체명\s*등록된\s*업체\s*맞나요\s*\?*\s*$"),
     "업체명 자리가 채워지지 않았어요. 실제 업체명으로 바꿔서 보내주세요. 예) '(주)한국소방기기 등록된 업체 맞나요?'"),
    (re.compile(r"^여기에\s*공문[·ㆍ]?안내문\s*내용을\s*붙여넣으세요\s*$"),
     "공문·안내문 내용이 비어 있어요. 실제 문구를 붙여넣어 보내주시거나, 입력창 옆 📷 버튼으로 사진을 업로드해주세요."),
]


def _extract_approval_number(text: str) -> str | None:
    num_m = APPROVAL_NUM_RE.search(text)
    if num_m:
        num_display = re.sub(r"\s+", "", num_m.group(0))
        type_m = APPROVAL_TYPE_RE.search(text)
        if type_m:
            type_word = re.sub(r"\s+", "", type_m.group(0))
            return f"{type_word} {num_display}"
        return num_display
    # 실 KFI 데이터 표기(예: "리소26-9")는 유형 접두어 없이 번호 자체가 DB 키이므로 그대로 반환한다.
    real_m = APPROVAL_NUM_RE_REAL.search(text)
    if real_m:
        return real_m.group(0)
    return None


def _extract_unit_code(text: str) -> str | None:
    m = UNIT_CODE_RE.search(text)
    if not m:
        return None
    return m.group(0).upper().replace(" ", "-")


def _extract_company(text: str) -> str | None:
    m = COMPANY_NAME_RE.search(text)
    return m.group(0) if m else None


def detect_and_run(message: str, user: dict | None = None) -> dict | None:
    """메시지에서 도구 호출 의도를 감지하면 {tool, args, result}를 반환하고,
    아무것도 감지되지 않으면 None을 반환한다(기존 RAG/LLM 흐름으로 폴백)."""
    text = (message or "").strip()
    if not text:
        return None

    approval_number = _extract_approval_number(text)
    if approval_number:
        result = kfi.get_approval(approval_number)
        if result.get("status") == "unregistered":
            loose = kfi.find_approval_loose(approval_number)
            if loose:
                result = loose
        return {"tool": "check_approval", "args": {"number": approval_number}, "result": result}

    if COMPANY_HINT_RE.search(text):
        company = _extract_company(text)
        if company:
            found = kfi.find_company(company)
            result = {"status": "registered", "data": found} if found else {"status": "unregistered"}
            return {"tool": "check_company", "args": {"name": company}, "result": result}

    unit_code = _extract_unit_code(text)
    if unit_code:
        ev = unit_service.evaluate_by_code(unit_code)
        if ev.get("found") and user:
            unit_service.register_unit(user["id"], unit_code)
            ev = {**ev, "registeredNow": True}
        return {"tool": "check_unit", "args": {"code": unit_code}, "result": ev}

    if user and (LOCKER_IMPERATIVE_RE.match(text) or LOCKER_REQUEST_RE.search(text)):
        items = unit_service.list_mine(user["id"])
        return {"tool": "list_units", "args": {}, "result": {"items": items}}

    if user and (NOTIF_IMPERATIVE_RE.match(text) or NOTIF_REQUEST_RE.search(text)):
        items = notification_service.list_mine(user["id"])
        return {"tool": "list_notifications", "args": {}, "result": {"items": items}}

    if len(text) >= 40 and not QUESTION_ENDING_RE.search(text) and any(k in text for k in DOC_KEYWORDS):
        doc = analyze_document(text)
        return {"tool": "analyze_doc", "args": {"text": text}, "result": doc}

    for pattern, hint in PLACEHOLDER_HINTS:
        if pattern.match(text):
            return {"tool": "placeholder_hint", "args": {}, "result": {"message": hint}}

    return None


def tool_result_as_context_block(tool_call: dict) -> str:
    """LLM 프롬프트에 주입할 [사실 판정 결과] 블록. LLM은 이 값을 그대로 설명만 해야 한다."""
    import json
    label = {
        "check_approval": "승인번호 조회 결과",
        "check_company": "업체 등록여부 조회 결과",
        "check_unit": "소화기(합격표시번호) 조회 결과",
        "analyze_doc": "공문/안내문 사기 위험도 분석 결과",
        "list_notifications": "내 알림 목록",
        "list_units": "내 소화기함 목록",
        "placeholder_hint": "빈칸이 채워지지 않은 입력에 대한 안내",
    }.get(tool_call["tool"], tool_call["tool"])
    return f"[방금 사용자 메시지에서 감지되어 실제 조회한 {label}]\n{json.dumps(tool_call['result'], ensure_ascii=False)}"


def format_tool_answer(tool_call: dict) -> str:
    """OPENAI_API_KEY가 없을 때도 바로 보여줄 수 있는 결정론적 한국어 설명."""
    tool = tool_call["tool"]
    result = tool_call["result"]

    if tool == "check_approval":
        if result.get("status") == "valid":
            d = result["data"]
            return (f"✅ 정상 등록된 승인번호입니다.\n"
                    f"인증종류: {d['type']}\n품목: {d['item']}\n업체: {d['company']}\n승인일: {d['approvedDate']}")
        if result.get("status") == "cancelled":
            d, c = result["data"], result["cancel"]
            return (f"🚨 취소(리콜)된 승인번호입니다.\n"
                    f"품목: {d['item']}\n업체: {d['company']}\n취소일: {c['cancelDate']}\n취소사유: {c['reason']}")
        return "🚨 KFI 승인정보에 등록되지 않은 번호입니다. 구매/입금 전에 다시 확인하시고, 의심되면 신고를 검토하세요."

    if tool == "check_company":
        if result.get("status") == "registered":
            d = result["data"]
            return f"✅ KFI 등록 {d['role']}입니다.\n대표자: {d['rep']}\n소재지: {d['address']}\n연락처: {d['phone']}"
        return "🚨 KFI 등록 업체 목록에서 확인되지 않는 업체입니다."

    if tool == "check_unit":
        if not result.get("found"):
            return "🚨 등록된 소화기 정보를 찾을 수 없습니다. 합격표시번호를 다시 확인해주세요."
        u = result["unit"]
        msg = f"{u['item']} (합격표시번호 {u['code']})\n현재 상태: {result['ageStatus']}"
        if result.get("recall"):
            msg += f"\n🚨 동일 형식 리콜 이력이 있습니다: {result['recall']['reason']}"
        if result.get("registeredNow"):
            msg += "\n📦 내 소화기함에 등록했습니다."
        elif not result.get("recall") and "즉시교체" not in result.get("ageStatus", ""):
            msg += "\n(로그인 후 다시 물어보시면 내 소화기함에 자동으로 등록해드립니다.)"
        return msg

    if tool == "analyze_doc":
        d = result
        msg = f"사기 위험도: {d['level']} ({d['score']}/100)"
        msg += "\n탐지된 패턴: " + ", ".join(d["matched"]) if d.get("matched") else "\n특이 위험 패턴은 없습니다."
        return msg

    if tool == "list_notifications":
        items = result.get("items") or []
        if not items:
            return "🔔 아직 쌓인 알림이 없습니다."
        lines = [f"- {n['created_at']} — {n['message']}" for n in items[:10]]
        more = f"\n(외 {len(items) - 10}건 더 있음)" if len(items) > 10 else ""
        return f"🔔 알림 {len(items)}건:\n" + "\n".join(lines) + more

    if tool == "list_units":
        items = result.get("items") or []
        if not items:
            return "📦 아직 등록된 소화기가 없습니다. 합격표시번호를 보내주시면 조회하면서 등록해드릴게요."
        lines = [f"- {u['unit']['code']} ({u['unit']['item']}) — {u['grade']}" for u in items]
        return f"📦 내 소화기함 ({len(items)}건):\n" + "\n".join(lines)

    if tool == "placeholder_hint":
        return result["message"]

    return ""
