from app.core.security import AuthBase
from app.models.user import User


def test_user_password_hashing_backend_is_available():
    password = "Strong!Pass123"

    hashed_password = User.get_password_hash(password)
    user = User(email="hash-test@example.com", hashed_password=hashed_password)

    assert hashed_password != password
    assert user.verify_password(password) is True
    assert user.verify_password("Wrong!Pass123") is False


def test_token_hashing_backend_is_available():
    token = "local-test-refresh-token"

    hashed_token = AuthBase.hash_token(token)

    assert hashed_token != token
    assert AuthBase.verify_token_hash(token, hashed_token) is True
    assert AuthBase.verify_token_hash("wrong-token", hashed_token) is False
