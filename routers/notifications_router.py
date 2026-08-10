from fastapi import APIRouter, Depends
from deps import require_auth
from services import notification_service
import db as db_module

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/mine")
def list_mine(user=Depends(require_auth)):
    return notification_service.list_mine(user["id"])


@router.patch("/{notif_id}/read")
def mark_read(notif_id: int, user=Depends(require_auth)):
    conn = db_module.get_conn()
    conn.execute("UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?", (notif_id, user["id"]))
    conn.commit()
    return {"ok": True}
