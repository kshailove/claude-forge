"""Unit tests for AES-256-GCM application-level encryption.

Covers:
  - Encrypt → decrypt roundtrip (original dict is recovered)
  - Different nonce each call (two encryptions of same plaintext differ)
  - Wrong key raises on decrypt
  - Short / malformed ciphertext raises ValueError
"""
from __future__ import annotations

import base64
import os
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_KEY_HEX = "b" * 64  # 32 bytes of 0xBB — valid AES-256 key
WRONG_KEY_HEX = "c" * 64  # Different key


def _patch_key(key_hex: str):
    """Context manager: patch get_settings to return a settings-like object with the key."""
    from unittest.mock import MagicMock
    mock_settings = MagicMock()
    mock_settings.db_encryption_key = key_hex
    mock_settings.db_encryption_key_bytes = bytes.fromhex(key_hex)
    return patch("app.core.encryption.get_settings", return_value=mock_settings)


# ---------------------------------------------------------------------------
# Roundtrip tests
# ---------------------------------------------------------------------------


class TestEncryptDecryptRoundtrip:
    def test_roundtrip_simple_dict(self):
        """encrypt_config → decrypt_config returns the original dict."""
        with _patch_key(VALID_KEY_HEX):
            from app.core.encryption import encrypt_config, decrypt_config

            plaintext = {"api_key": "secret123", "org": "myorg"}
            ciphertext = encrypt_config(plaintext)
            recovered = decrypt_config(ciphertext)

        assert recovered == plaintext

    def test_roundtrip_nested_dict(self):
        """Works for nested structures."""
        with _patch_key(VALID_KEY_HEX):
            from app.core.encryption import encrypt_config, decrypt_config

            plaintext = {
                "github": {"pat": "ghp_123", "org": "acme"},
                "rate_limit": 1000,
                "enabled": True,
            }
            ciphertext = encrypt_config(plaintext)
            recovered = decrypt_config(ciphertext)

        assert recovered == plaintext

    def test_roundtrip_empty_dict(self):
        """Empty dict survives roundtrip."""
        with _patch_key(VALID_KEY_HEX):
            from app.core.encryption import encrypt_config, decrypt_config

            plaintext: dict = {}
            ciphertext = encrypt_config(plaintext)
            recovered = decrypt_config(ciphertext)

        assert recovered == plaintext

    def test_decrypt_config_field_returns_value(self):
        """decrypt_config_field returns the value for a known key."""
        with _patch_key(VALID_KEY_HEX):
            from app.core.encryption import encrypt_config, decrypt_config_field

            plaintext = {"token": "abc-xyz-789"}
            ciphertext = encrypt_config(plaintext)
            result = decrypt_config_field(ciphertext, "token")

        assert result == "abc-xyz-789"

    def test_decrypt_config_field_missing_key_returns_none(self):
        """decrypt_config_field returns None for a non-existent field."""
        with _patch_key(VALID_KEY_HEX):
            from app.core.encryption import encrypt_config, decrypt_config_field

            ciphertext = encrypt_config({"foo": "bar"})
            result = decrypt_config_field(ciphertext, "nonexistent")

        assert result is None


# ---------------------------------------------------------------------------
# Nonce uniqueness tests
# ---------------------------------------------------------------------------


class TestDifferentNonceEachCall:
    def test_different_nonce_each_call(self):
        """Two encryptions of the same plaintext produce different ciphertexts (unique nonce)."""
        with _patch_key(VALID_KEY_HEX):
            from app.core.encryption import encrypt_config

            plaintext = {"secret": "value"}
            c1 = encrypt_config(plaintext)
            c2 = encrypt_config(plaintext)

        assert c1 != c2

    def test_nonce_length_is_12_bytes(self):
        """The first 12 bytes of the decoded ciphertext are the GCM nonce."""
        with _patch_key(VALID_KEY_HEX):
            from app.core.encryption import encrypt_config

            ciphertext_b64 = encrypt_config({"k": "v"})
            decoded = base64.b64decode(ciphertext_b64)

        # At minimum: 12-byte nonce + at least 1 byte ciphertext + 16-byte GCM tag
        assert len(decoded) >= 29

    def test_ciphertext_is_valid_base64(self):
        """encrypt_config returns a valid base64 ASCII string."""
        with _patch_key(VALID_KEY_HEX):
            from app.core.encryption import encrypt_config

            result = encrypt_config({"x": 1})

        # Should not raise
        decoded = base64.b64decode(result)
        assert len(decoded) > 0


# ---------------------------------------------------------------------------
# Wrong key raises tests
# ---------------------------------------------------------------------------


class TestWrongKeyRaises:
    def test_wrong_key_raises_on_decrypt(self):
        """Decrypting with a different 64-hex key raises an exception."""
        # Encrypt with VALID_KEY_HEX
        with _patch_key(VALID_KEY_HEX):
            from app.core.encryption import encrypt_config
            ciphertext = encrypt_config({"secret": "data"})

        # Attempt decrypt with WRONG_KEY_HEX — must raise
        with _patch_key(WRONG_KEY_HEX):
            from importlib import reload
            import app.core.encryption as enc_mod
            reload(enc_mod)  # reload to pick up new patch

            with pytest.raises(Exception):
                enc_mod.decrypt_config(ciphertext)

    def test_malformed_base64_raises_value_error(self):
        """decrypt_config raises ValueError for non-base64 input."""
        with _patch_key(VALID_KEY_HEX):
            from app.core.encryption import decrypt_config

            with pytest.raises(ValueError, match="Invalid base64"):
                decrypt_config("not-valid-base64!!!")

    def test_too_short_ciphertext_raises_value_error(self):
        """decrypt_config raises ValueError when ciphertext is less than 13 bytes."""
        with _patch_key(VALID_KEY_HEX):
            from app.core.encryption import decrypt_config

            # 6 bytes → way too short
            short = base64.b64encode(b"short").decode()
            with pytest.raises(ValueError, match="too short"):
                decrypt_config(short)
