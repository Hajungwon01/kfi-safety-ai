from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import kfi_client as kfi
from doc_analyzer import analyze_document

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


class AnalyzeDocBody(BaseModel):
    text: str = ""


@router.post("/analyze-doc")
def analyze_doc(body: AnalyzeDocBody):
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="text가 필요합니다.")
    return analyze_document(body.text)


@router.get("/{number}")
def get_approval(number: str):
    try:
        return kfi.get_approval(number)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
