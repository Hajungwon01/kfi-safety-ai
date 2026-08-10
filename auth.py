"""인증 로직: bcrypt 비밀번호 해시 + JWT 발급/검증 (FastAPI는 세션이 없는 stateless REST API이므로
Node판과 동일하게 JWT를 다시 사용한다)."""
import os
import time
import bcrypt
import jwt as pyjwt
import db as db_module

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
JWT_ALGO = "HS256"
JWT_EXPIRES_SECONDS = 7 * 24 * 3600  # 7일


class AuthError(Exception):
    pass


def _sign(user: dict) -> str:
    payload = {"id": user["id"], "email": user["email"], "role": user["role"], "exp": int(time.time()) + JWT_EXPIRES_SECONDS}
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def verify_token(token: str) -> dict:
    try:
        return pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except pyjwt.PyJWTError as e:
        raise AuthError(f"토큰이 유효하지 않습니다: {e}")


def register_user(email: str, password: str, role: str = "facility_manager") -> tuple[dict, str]:
    email = (email or "").strip()
    if not email or not password:
        raise AuthError("이메일/비밀번호를 입력하세요.")
    conn = db_module.get_conn()
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        raise AuthError("이미 가입된 이메일입니다.")
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    cur = conn.execute("INSERT INTO users (email, password_hash, role) VALUES (?,?,?)", (email, pw_hash, role))
    conn.commit()
    user = {"id": cur.lastrowid, "email": email, "role": role}
    return user, _sign(user)


def login_user(email: str, password: str) -> tuple[dict, str]:
    email = (email or "").strip()
    conn = db_module.get_conn()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not row:
        raise AuthError("등록되지 않은 이메일입니다.")
    if not bcrypt.checkpw((password or "").encode("utf-8"), row["password_hash"].encode("utf-8")):
        raise AuthError("비밀번호가 일치하지 않습니다.")
    user = {"id": row["id"], "email": row["email"], "role": row["role"]}
    return user, _sign(user)
