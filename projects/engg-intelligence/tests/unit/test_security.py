"""Unit tests for JWT token creation/validation and bcrypt password hashing.

Covers:
  - Access token encode → decode roundtrip (claims match)
  - Expired token detection
  - Wrong-secret rejection
  - bcrypt hash + verify (correct and wrong password)
  - Refresh token generation and SHA-256 hashing
"""
from __future__ import annotations

import time
import uuid
from unittest.mock import patch

import pytest
from jose import JWTError, jwt


# ---------------------------------------------------------------------------
# Token tests
# ---------------------------------------------------------------------------


class TestCreateAndVerifyAccessToken:
    def test_create_and_verify_access_token_claims_match(self):
        """Encoded token decodes to the same sub, role, and team_id."""
        from app.core.security import create_access_token, decode_access_token

        user_id = uuid.uuid4()
        team_id = uuid.uuid4()

        token = create_access_token(user_id=user_id, role="em", team_id=team_id)
        payload = decode_access_token(token)

        assert payload["sub"] == str(user_id)
        assert payload["role"] == "em"
        assert payload["team_id"] == str(team_id)

    def test_create_access_token_without_team_id_encodes_none(self):
        """Tokens for admin/director roles with no team encode team_id=None."""
        from app.core.security import create_access_token, decode_access_token

        token = create_access_token(user_id=uuid.uuid4(), role="admin", team_id=None)
        payload = decode_access_token(token)

        assert payload["team_id"] is None

    def test_create_access_token_contains_jti(self):
        """Each token has a unique jti claim."""
        from app.core.security import create_access_token, decode_access_token

        t1 = create_access_token(user_id=uuid.uuid4(), role="engineer")
        t2 = create_access_token(user_id=uuid.uuid4(), role="engineer")

        p1 = decode_access_token(t1)
        p2 = decode_access_token(t2)

        assert p1["jti"] != p2["jti"]

    def test_create_access_token_contains_iat_and_exp(self):
        """Token payload contains iat and exp integer epoch timestamps."""
        from app.core.security import create_access_token, decode_access_token

        before = int(time.time())
        token = create_access_token(user_id=uuid.uuid4(), role="director")
        after = int(time.time())
        payload = decode_access_token(token)

        assert before <= payload["iat"] <= after
        assert payload["exp"] > payload["iat"]


class TestExpiredToken:
    def test_expired_token_raises_jwt_error(self):
        """A token with exp in the past raises JWTError on decode."""
        from app.core.security import ALGORITHM, decode_access_token
        from app.core.config import get_settings

        settings = get_settings()
        expired_payload = {
            "sub": str(uuid.uuid4()),
            "role": "engineer",
            "team_id": None,
            "jti": str(uuid.uuid4()),
            "iat": int(time.time()) - 7200,
            "exp": int(time.time()) - 3600,  # already expired
        }
        expired_token = jwt.encode(expired_payload, settings.jwt_secret, algorithm=ALGORITHM)

        with pytest.raises(JWTError):
            decode_access_token(expired_token)


class TestWrongSecret:
    def test_wrong_secret_raises_jwt_error(self):
        """Decoding a token with a different secret raises JWTError."""
        from app.core.security import ALGORITHM, decode_access_token
        from app.core.config import get_settings

        settings = get_settings()
        payload = {
            "sub": str(uuid.uuid4()),
            "role": "engineer",
            "team_id": None,
            "jti": str(uuid.uuid4()),
            "iat": int(time.time()),
            "exp": int(time.time()) + 86400,
        }
        token_with_wrong_secret = jwt.encode(
            payload, "completely-different-secret-for-testing!!", algorithm=ALGORITHM
        )

        with pytest.raises(JWTError):
            decode_access_token(token_with_wrong_secret)


# ---------------------------------------------------------------------------
# Password hashing tests
# ---------------------------------------------------------------------------


class TestBcryptHashing:
    def test_bcrypt_verify_correct_password_returns_true(self):
        """hash_password + verify_password returns True for the original password."""
        from app.core.security import hash_password, verify_password

        plain = "MySecureP@ssword1!"
        hashed = hash_password(plain)

        assert verify_password(plain, hashed) is True

    def test_bcrypt_reject_wrong_password_returns_false(self):
        """verify_password returns False when the wrong password is supplied."""
        from app.core.security import hash_password, verify_password

        hashed = hash_password("CorrectPassword!")

        assert verify_password("WrongPassword!", hashed) is False

    def test_bcrypt_hash_is_not_plaintext(self):
        """The hash does not contain the original plaintext."""
        from app.core.security import hash_password

        plain = "MyPassword"
        hashed = hash_password(plain)

        assert plain not in hashed
        assert hashed.startswith("$2b$")

    def test_bcrypt_two_hashes_of_same_password_differ(self):
        """bcrypt uses a random salt so two hashes of the same password differ."""
        from app.core.security import hash_password

        plain = "SamePassword"
        h1 = hash_password(plain)
        h2 = hash_password(plain)

        assert h1 != h2


# ---------------------------------------------------------------------------
# Refresh token helpers
# ---------------------------------------------------------------------------


class TestRefreshToken:
    def test_generate_refresh_token_is_urlsafe_string(self):
        """generate_refresh_token returns a non-empty URL-safe string."""
        from app.core.security import generate_refresh_token

        token = generate_refresh_token()
        assert isinstance(token, str)
        assert len(token) > 32

    def test_hash_refresh_token_is_sha256_hex(self):
        """hash_refresh_token returns a 64-character lowercase hex string."""
        from app.core.security import generate_refresh_token, hash_refresh_token

        token = generate_refresh_token()
        token_hash = hash_refresh_token(token)

        assert len(token_hash) == 64
        assert all(c in "0123456789abcdef" for c in token_hash)

    def test_hash_refresh_token_deterministic(self):
        """Same input always produces the same SHA-256 hash."""
        from app.core.security import hash_refresh_token

        token = "fixed-test-token-value"
        assert hash_refresh_token(token) == hash_refresh_token(token)

    def test_refresh_token_expires_at_is_future(self):
        """refresh_token_expires_at() returns a datetime in the future."""
        import time
        from app.core.security import refresh_token_expires_at

        expires = refresh_token_expires_at()
        assert expires > datetime.now(tz=expires.tzinfo)


# Needed for datetime import inside test method
from datetime import datetime
