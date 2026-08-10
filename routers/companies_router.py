from fastapi import APIRouter
import kfi_client as kfi

router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.get("/{name}")
def get_company(name: str):
    found = kfi.find_company(name)
    if found:
        return {"status": "registered", "data": found}
    return {"status": "unregistered"}
