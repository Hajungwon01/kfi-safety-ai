from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterBody(BaseModel):
    email: str
    password: str


class LoginBody(BaseModel):
    email: str
    password: str


@router.post("/register")
def register(body: RegisterBody):
    # 관리자 권한은 셀프 회원가입으로 부여되지 않는다(클라이언트가 role을 지정해도 무시).
    # 관제 대시보드 등 관리자 기능은 시딩된 관리자 계정으로만 접근 가능.
    try:
        user, token = auth.register_user(body.email, body.password, "facility_manager")
    except auth.AuthError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"user": user, "token": token}


@router.post("/login")
def login(body: LoginBody):
    try:
        user, token = auth.login_user(body.email, body.password)
    except auth.AuthError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"user": user, "token": token}
