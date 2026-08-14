import logging
import threading
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

logger = logging.getLogger("startup_sync")

app = FastAPI(title="소방용품 안전지킴이 AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


@app.on_event("startup")
def sync_kfi_on_startup():
    """Railway 등 컨테이너 배포는 파일시스템이 재시작/재배포마다 초기화되어 SQLite에 쌓아둔
    실 KFI 동기화 데이터가 매번 사라진다(볼륨 미마운트 시). USE_MOCK=false + 서비스키가 설정된
    경우, 기동 시 백그라운드 스레드로 자동 재동기화해서 이 문제를 보완한다.
    헬스체크(/api/health) 응답을 막지 않도록 별도 스레드에서 실행한다."""
    if kfi.USE_MOCK or not kfi.SERVICE_KEY:
        return

    def _run():
        try:
            result = kfi.sync_all()
            logger.info("startup sync-kfi 완료: %s", result)
        except Exception as e:
            logger.warning("startup sync-kfi 실패(다음 기동 또는 수동 /api/admin/sync-kfi 재시도 필요): %s", e)

    threading.Thread(target=_run, daemon=True).start()


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
