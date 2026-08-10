from fastapi import APIRouter, Depends, HTTPException
from deps import require_auth
from services import unit_service

router = APIRouter(prefix="/api/units", tags=["units"])


@router.get("/mine")
def list_mine(user=Depends(require_auth)):
    return unit_service.list_mine(user["id"])


@router.get("/{code}")
def get_unit(code: str):
    return unit_service.evaluate_by_code(code)


@router.post("/{code}/register", status_code=201)
def register_unit(code: str, user=Depends(require_auth)):
    result = unit_service.register_unit(user["id"], code)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result
