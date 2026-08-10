from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import kfi_client as kfi
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
