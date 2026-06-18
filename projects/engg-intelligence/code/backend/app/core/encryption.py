"""AES-256-GCM application-level encryption for integrations.config_json.

The encryption key (DB_ENCRYPTION_KEY) never touches the database — it lives
exclusively in the application process and is loaded from the environment.

Spec reference: §7.7 Application-Level Encryption

Key format: 64-character hex string (32 bytes → AES-256 key).
Ciphertext format: base64(nonce[12] + ciphertext_with_tag)
"""
from __future__ import annotations

import base64
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings


def _get_aesgcm() -> AESGCM:
    """Return an AESGCM instance initialised with the configured key."""
    key_bytes = get_settings().db_encryption_key_bytes
    return AESGCM(key_bytes)


def encrypt_config(plaintext: dict) -> str:
    """Encrypt a config dict and return a base64-encoded ciphertext string.

    Storage format: base64(nonce[12 bytes] + ciphertext_with_gcm_tag)
    """
    json_bytes = json.dumps(plaintext, separators=(",", ":")).encode("utf-8")
    nonce = os.urandom(12)  # 96-bit nonce — unique per encryption, never reused
    aesgcm = _get_aesgcm()
    ciphertext = aesgcm.encrypt(nonce, json_bytes, associated_data=None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_config(encrypted: str) -> dict:
    """Decrypt a base64-encoded ciphertext string and return the original dict.

    Raises:
        ValueError: if the ciphertext is malformed or authentication fails.
        cryptography.exceptions.InvalidTag: if the GCM tag is invalid
            (data corrupted or wrong key).
    """
    try:
        data = base64.b64decode(encrypted)
    except Exception as exc:
        raise ValueError("Invalid base64 in encrypted config_json") from exc

    if len(data) < 13:  # nonce (12) + min 1 byte ciphertext
        raise ValueError("Encrypted config_json is too short to be valid")

    nonce, ciphertext = data[:12], data[12:]
    aesgcm = _get_aesgcm()
    plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
    return json.loads(plaintext.decode("utf-8"))


def decrypt_config_field(encrypted: str, field: str) -> str | None:
    """Convenience: decrypt config and return a single field value (or None)."""
    config = decrypt_config(encrypted)
    return config.get(field)
