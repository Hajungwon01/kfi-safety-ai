"""FastAPI 의존성: Authorization 헤더에서 JWT를 검증해 현재 사용자를 주입."""
from fastapi import Header, HTTPException, Depends
import auth


def require_auth(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    token = authorization[len("Bearer "):]
    try:
        return auth.verify_token(token)
    except auth.AuthError:
        raise HTTPException(status_code=401, detail="토큰이 유효하지 않습니다.")


def require_admin(user: dict = Depends(require_auth)) -> dict:
    """관제 대시보드/관리자 액션 전용. role이 admin이 아니면 403."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="관리자만 접근할 수 있습니다.")
    return user


def soft_auth(authorization: str | None = Header(default=None)) -> dict | None:
    """토큰이 있으면 검증해서 사용자 정보를 반환하고, 없거나 유효하지 않으면 조용히 None (비로그인 허용)."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[len("Bearer "):]
    try:
        return auth.verify_token(token)
    except auth.AuthError:
        return None
