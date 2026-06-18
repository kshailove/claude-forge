"""Command-line interface for engg-intelligence administrative tasks.

Usage:
    python -m app.cli --help
    python -m app.cli create-admin
    python -m app.cli rotate-encryption-key --old-key <hex> --new-key <hex>

Run inside the API container:
    docker-compose exec api python -m app.cli create-admin
"""
from __future__ import annotations

import getpass
import logging
import sys

import click
from sqlalchemy import select, text

from app.core.database import SyncSessionLocal
from app.core.encryption import decrypt_config, encrypt_config
from app.core.security import hash_password
from app.models.integration import Integration

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
def cli() -> None:
    """engg-intelligence administration CLI."""


# ---------------------------------------------------------------------------
# create-admin command
# ---------------------------------------------------------------------------

@cli.command("create-admin")
@click.option("--email", prompt="Admin email", help="Email address for the new admin user")
@click.option(
    "--password",
    default=None,
    help="Password (prompted interactively if omitted)",
)
def create_admin(email: str, password: str | None) -> None:
    """Create an admin user interactively.

    Example:
        docker-compose exec api python -m app.cli create-admin
    """
    # Lazy import to avoid circular deps at module load time
    from app.models.user import User  # noqa: PLC0415

    if password is None:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            click.echo("Passwords do not match.", err=True)
            sys.exit(1)

    if len(password) < 8:
        click.echo("Password must be at least 8 characters.", err=True)
        sys.exit(1)

    with SyncSessionLocal() as session:
        existing = session.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": email},
        ).fetchone()

        if existing:
            click.echo(f"User with email {email!r} already exists.", err=True)
            sys.exit(1)

        username = email.split("@")[0]
        hashed = hash_password(password)
        session.execute(
            text(
                """
                INSERT INTO users (email, username, password_hash, role, is_active, created_at, updated_at)
                VALUES (:email, :username, :password_hash, 'admin', true, now(), now())
                """
            ),
            {"email": email, "username": username, "password_hash": hashed},
        )
        session.commit()

    click.echo(f"Admin user {email!r} created successfully.")


# ---------------------------------------------------------------------------
# rotate-encryption-key command
# ---------------------------------------------------------------------------

@cli.command("rotate-encryption-key")
@click.option(
    "--old-key",
    required=True,
    envvar="OLD_DB_ENCRYPTION_KEY",
    help="Current AES-256 key as 64-character hex string (or set OLD_DB_ENCRYPTION_KEY env var)",
)
@click.option(
    "--new-key",
    required=True,
    envvar="NEW_DB_ENCRYPTION_KEY",
    help="New AES-256 key as 64-character hex string (or set NEW_DB_ENCRYPTION_KEY env var)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print how many rows would be updated without modifying the database",
)
def rotate_encryption_key(old_key: str, new_key: str, dry_run: bool) -> None:
    """Re-encrypt all integrations.config_json from OLD_KEY to NEW_KEY.

    The rotation runs inside a single database transaction. If any row
    fails to decrypt or re-encrypt, the entire transaction is rolled back
    and no rows are modified.

    Steps:
    1.  Fetch all rows from the integrations table.
    2.  Decrypt each config_json with --old-key.
    3.  Re-encrypt with --new-key.
    4.  UPDATE the row with the new ciphertext.
    5.  Commit once all rows succeed (or rollback on any error).

    After a successful rotation:
    - Replace DB_ENCRYPTION_KEY in your environment / Kubernetes Secret.
    - Restart all API and Celery pods so they pick up the new key.

    Example:
        python -m app.cli rotate-encryption-key \\
            --old-key $(printenv OLD_DB_ENCRYPTION_KEY) \\
            --new-key $(printenv NEW_DB_ENCRYPTION_KEY)
    """
    # Validate key format
    for label, key in [("old", old_key), ("new", new_key)]:
        if len(key) != 64:
            click.echo(
                f"--{label}-key must be exactly 64 hex characters (got {len(key)})",
                err=True,
            )
            sys.exit(1)
        try:
            bytes.fromhex(key)
        except ValueError:
            click.echo(f"--{label}-key is not valid hex", err=True)
            sys.exit(1)

    if old_key == new_key:
        click.echo("Old key and new key are identical — nothing to do.")
        sys.exit(0)

    import base64
    import os as _os

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    old_key_bytes = bytes.fromhex(old_key)
    new_key_bytes = bytes.fromhex(new_key)

    def _decrypt_with_key(encrypted: str, key_bytes: bytes) -> dict:
        data = base64.b64decode(encrypted)
        nonce, ciphertext = data[:12], data[12:]
        aesgcm = AESGCM(key_bytes)
        import json
        plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
        return json.loads(plaintext.decode("utf-8"))

    def _encrypt_with_key(config: dict, key_bytes: bytes) -> str:
        import json
        json_bytes = json.dumps(config, separators=(",", ":")).encode("utf-8")
        nonce = _os.urandom(12)
        aesgcm = AESGCM(key_bytes)
        ciphertext = aesgcm.encrypt(nonce, json_bytes, associated_data=None)
        return base64.b64encode(nonce + ciphertext).decode("ascii")

    with SyncSessionLocal() as session:
        rows = session.execute(
            text("SELECT id, config_json FROM integrations ORDER BY id")
        ).fetchall()

        total = len(rows)
        click.echo(f"Found {total} integration row(s) to re-encrypt.")

        if dry_run:
            click.echo("[dry-run] No changes will be written to the database.")

        updated = 0
        errors = 0

        for row in rows:
            row_id, config_json = row.id, row.config_json
            try:
                plaintext = _decrypt_with_key(config_json, old_key_bytes)
                new_ciphertext = _encrypt_with_key(plaintext, new_key_bytes)
                if not dry_run:
                    session.execute(
                        text(
                            "UPDATE integrations SET config_json = :ciphertext, updated_at = now() "
                            "WHERE id = :id"
                        ),
                        {"ciphertext": new_ciphertext, "id": str(row_id)},
                    )
                updated += 1
            except Exception as exc:  # noqa: BLE001
                click.echo(f"  ERROR row {row_id}: {exc}", err=True)
                errors += 1
                if not dry_run:
                    # Roll back entire transaction on any failure
                    session.rollback()
                    click.echo(
                        "Transaction rolled back — no rows were modified.",
                        err=True,
                    )
                    sys.exit(1)

        if not dry_run and errors == 0:
            session.commit()
            click.echo(
                f"Key rotation complete. {updated}/{total} rows re-encrypted and committed."
            )
        elif dry_run:
            click.echo(
                f"[dry-run] Would re-encrypt {updated}/{total} rows. {errors} error(s)."
            )
        else:
            click.echo(f"Rotation failed with {errors} error(s).", err=True)
            sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cli()
