from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from deps import soft_auth, require_admin
from services import report_service

router = APIRouter(prefix="/api/reports", tags=["reports"])


class ReportBody(BaseModel):
    type: str
    region: str | None = None
    target: str | None = None
    reason: str | None = None
    riskLevel: str | None = None


@router.post("", status_code=201)
def submit_report(body: ReportBody, user=Depends(soft_auth)):
    if body.type not in ("fraud", "maintenance"):
        raise HTTPException(status_code=400, detail="type은 fraud 또는 maintenance여야 합니다.")
    report_id = report_service.submit_report(
        user_id=user["id"] if user else None, type_=body.type, region=body.region,
        target=body.target, reason=body.reason, risk_level=body.riskLevel,
    )
    return {"id": report_id}


@router.get("")
def list_reports(user=Depends(require_admin)):
    return report_service.list_reports()


@router.get("/stats")
def stats(user=Depends(require_admin)):
    return report_service.stats()
