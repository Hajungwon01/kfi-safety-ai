"""데모/관리자용: 리콜(승인취소) 수동 트리거 (Node판 routes/admin.js의 simulate-recall 포팅).
실서비스라면 KFI 취소정보 sync 배치가 신규 취소 건을 감지해 자동 트리거해야 하는 것을, 시연 편의를 위해
수동 트리거 함수로 제공."""
import db as db_module
import kfi_client as kfi
from services import notification_service

DEMO_RECALL_NUMBER = "성능인증 제2023-7-118호"
DEMO_RECALL_REASON = "소화성능 재검증 결과 기준 미달"


def simulate_recall(number: str = DEMO_RECALL_NUMBER, reason: str = None) -> dict:
    conn = db_module.get_conn()
    row = conn.execute("SELECT * FROM approval_cache WHERE number=?", (number,)).fetchone()
    if not row:
        return {"error": f"해당 승인번호가 approval_cache에 없습니다: {number}"}
    if row["cancelled"]:
        return {"error": "이미 취소 처리된 승인번호입니다."}
    cancel_reason = reason or DEMO_RECALL_REASON
    kfi.mark_approval_cancelled(number, cancel_reason)
    result = notification_service.notify_affected_users(number, row["item"], cancel_reason)
    return {"ok": True, "number": number, **result}
