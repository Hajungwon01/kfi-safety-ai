import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["DB_PATH"] = ":memory:"

import db as db_module
import auth
import pytest


def setup_function():
    db_module.reset_conn()


def test_register_then_login():
    user, token = auth.register_user("a@example.com", "pw1234")
    assert user["email"] == "a@example.com"
    assert token
    decoded = auth.verify_token(token)
    assert decoded["email"] == "a@example.com"
    logged_user, token2 = auth.login_user("a@example.com", "pw1234")
    assert logged_user["id"] == user["id"]
    assert token2


def test_duplicate_email_rejected():
    auth.register_user("dup@example.com", "pw1234")
    with pytest.raises(auth.AuthError):
        auth.register_user("dup@example.com", "pw1234")


def test_wrong_password_rejected():
    auth.register_user("b@example.com", "correct-pw")
    with pytest.raises(auth.AuthError):
        auth.login_user("b@example.com", "wrong-pw")


def test_unknown_email_rejected():
    with pytest.raises(auth.AuthError):
        auth.login_user("nope@example.com", "pw")


def test_invalid_token_rejected():
    with pytest.raises(auth.AuthError):
        auth.verify_token("not-a-real-token")
