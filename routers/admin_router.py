from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import kfi_client as kfi
import db as db_module
from services import recall_service
from deps import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


class SimulateRecallBody(BaseModel):
    number: str | None = None
    reason: str | None = None


@router.post("/simulate-recall")
def simulate_recall(body: SimulateRecallBody, user=Depends(require_admin)):
    kwargs = {}
    if body.number:
        kwargs["number"] = body.number
    if body.reason:
        kwargs["reason"] = body.reason
    result = recall_service.simulate_recall(**kwargs)
    if result.get("error"):
        status = 409 if "이미 취소" in result["error"] else 404
        raise HTTPException(status_code=status, detail=result["error"])
    return result


class SyncKfiBody(BaseModel):
    fromAprv: str | None = None
    toAprv: str | None = None
    gdsClCodes: list[str] | None = None


@router.post("/sync-kfi")
def sync_kfi(body: SyncKfiBody, user=Depends(require_admin)):
    if kfi.USE_MOCK:
        raise HTTPException(status_code=400, detail="USE_MOCK=true 상태입니다. .env에서 USE_MOCK=false, KFI_SERVICE_KEY 설정 후 다시 시도하세요.")
    try:
        return kfi.sync_all(from_aprv=body.fromAprv, to_aprv=body.toAprv, gds_cl_codes=body.gdsClCodes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sample-data")
def sample_data(limit: int = 5, user=Depends(require_admin)):
    """데모 준비용: 지금 DB에 실제로 들어있는 값 몇 개를 그대로 보여준다.
    (조회 로직을 타지 않고 캐시 테이블을 직접 SELECT하므로 mock/실 API 여부와 무관하게
    '지금 이 순간 실제로 조회에 성공하는 값'을 정확히 확인할 수 있다.)"""
    conn = db_module.get_conn()
    valid_approvals = conn.execute(
        "SELECT number, type, item, company FROM approval_cache WHERE cancelled=0 ORDER BY synced_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    cancelled_approvals = conn.execute(
        "SELECT number, type, item, company, cancel_date, cancel_reason FROM approval_cache WHERE cancelled=1 ORDER BY synced_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    companies = conn.execute(
        "SELECT name, role, rep, address, phone FROM companies LIMIT ?", (limit,)
    ).fetchall()
    units = conn.execute(
        "SELECT code, item, first_approved, maker FROM units LIMIT ?", (limit,)
    ).fetchall()
    counts = {
        "approval_cache": conn.execute("SELECT COUNT(*) c FROM approval_cache").fetchone()["c"],
        "companies": conn.execute("SELECT COUNT(*) c FROM companies").fetchone()["c"],
        "units": conn.execute("SELECT COUNT(*) c FROM units").fetchone()["c"],
    }
    return {
        "counts": counts,
        "validApprovals": [dict(r) for r in valid_approvals],
        "cancelledApprovals": [dict(r) for r in cancelled_approvals],
        "companies": [dict(r) for r in companies],
        "units": [dict(r) for r in units],
    }
