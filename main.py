from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import kfi_client as kfi
from routers import (
    auth_router, approvals_router, companies_router, units_router,
    reports_router, notifications_router, admin_router, chat_router,
)

app = FastAPI(title="소방용품 안전지킴이 AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True, "mockMode": kfi.USE_MOCK}


app.include_router(auth_router.router)
app.include_router(approvals_router.router)
app.include_router(companies_router.router)
app.include_router(units_router.router)
app.include_router(reports_router.router)
app.include_router(notifications_router.router)
app.include_router(admin_router.router)
app.include_router(chat_router.router)

PUBLIC_DIR = Path(__file__).parent / "public"
if PUBLIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(PUBLIC_DIR), html=True), name="public")
