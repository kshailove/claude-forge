"""Digest sender — delivers rendered HTML emails via SendGrid or SMTP fallback.

Priority:
  1. SendGrid HTTP API v3 (if SENDGRID_API_KEY is set)
  2. SMTP via aiosmtplib  (if SMTP_HOST is set)
  3. Log only           (neither configured — development mode)

Spec §8 M7b.
"""
from __future__ import annotations

import email.mime.multipart
import email.mime.text
from datetime import datetime, timezone
from uuid import UUID

import httpx
import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.digest import DigestEmail, DigestRun
from app.models.user import User

logger = structlog.get_logger(__name__)


class DigestSender:
    """Sends digest emails and updates delivery status in the database."""

    async def send_digest(
        self,
        user_id: str,
        digest_run_id: str,
        db: AsyncSession,
    ) -> bool:
        """Fetch rendered HTML from digest_emails and deliver it.

        Returns True on success, False on failure.
        Updates delivery_status on the DigestEmail row.
        """
        settings = get_settings()

        user_uuid = UUID(user_id)
        run_uuid = UUID(digest_run_id)

        # Load user
        user_result = await db.execute(select(User).where(User.id == user_uuid))
        user: User | None = user_result.scalar_one_or_none()
        if user is None:
            logger.error("digest_send_user_not_found", user_id=user_id)
            return False

        # Load digest email record
        email_result = await db.execute(
            select(DigestEmail).where(
                and_(
                    DigestEmail.user_id == user_uuid,
                    DigestEmail.digest_run_id == run_uuid,
                )
            )
        )
        digest_email: DigestEmail | None = email_result.scalar_one_or_none()
        if digest_email is None:
            logger.error(
                "digest_send_record_not_found",
                user_id=user_id,
                digest_run_id=digest_run_id,
            )
            return False

        # Build subject
        now = datetime.now(tz=timezone.utc)
        subject = f"Engineering Weekly — {now.strftime('%b %d, %Y')}"

        # Attempt delivery
        success = False
        error_detail: str | None = None

        if settings.sendgrid_api_key:
            success, error_detail = await self._send_via_sendgrid(
                to_email=user.email,
                subject=subject,
                html_content=digest_email.html_content,
                api_key=settings.sendgrid_api_key,
                from_email=settings.smtp_from_address,
            )
        elif settings.smtp_host:
            success, error_detail = await self._send_via_smtp(
                to_email=user.email,
                subject=subject,
                html_content=digest_email.html_content,
                host=settings.smtp_host,
                port=settings.smtp_port,
                user=settings.smtp_user,
                password=settings.smtp_password,
                from_address=settings.smtp_from_address,
            )
        else:
            # Development mode — no delivery configured
            logger.info(
                "digest_send_skipped_no_transport",
                user_id=user_id,
                subject=subject,
                hint="Set SENDGRID_API_KEY or SMTP_HOST to enable delivery",
            )
            success = True  # Mark as sent in dev mode so pipeline continues

        # Persist result
        if success:
            digest_email.delivery_status = "sent"
            digest_email.sent_at = datetime.now(tz=timezone.utc)
        else:
            digest_email.delivery_status = "failed"
            if error_detail:
                # Store truncated error in sendgrid_message_id field (reuse for error notes)
                digest_email.sendgrid_message_id = error_detail[:255]

        await db.commit()

        log_fn = logger.info if success else logger.error
        log_fn(
            "digest_send_result",
            user_id=user_id,
            success=success,
            error=error_detail,
        )
        return success

    # -----------------------------------------------------------------------
    # SendGrid
    # -----------------------------------------------------------------------

    async def _send_via_sendgrid(
        self,
        *,
        to_email: str,
        subject: str,
        html_content: str,
        api_key: str,
        from_email: str,
    ) -> tuple[bool, str | None]:
        """POST to SendGrid Mail Send API v3.

        Returns (success, error_detail).
        """
        payload = {
            "personalizations": [
                {"to": [{"email": to_email}]}
            ],
            "from": {"email": from_email},
            "subject": subject,
            "content": [{"type": "text/html", "value": html_content}],
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )

            if response.status_code == 202:
                message_id = response.headers.get("X-Message-Id", "")
                logger.info(
                    "sendgrid_send_ok",
                    to=to_email,
                    message_id=message_id,
                )
                return True, None

            # 4xx / 5xx error
            error_body = response.text[:500]
            logger.error(
                "sendgrid_send_failed",
                to=to_email,
                status_code=response.status_code,
                body=error_body,
            )
            return False, f"HTTP {response.status_code}: {error_body}"

        except httpx.RequestError as exc:
            logger.error("sendgrid_request_error", to=to_email, error=str(exc))
            return False, str(exc)

    # -----------------------------------------------------------------------
    # SMTP fallback
    # -----------------------------------------------------------------------

    async def _send_via_smtp(
        self,
        *,
        to_email: str,
        subject: str,
        html_content: str,
        host: str,
        port: int,
        user: str | None,
        password: str | None,
        from_address: str,
    ) -> tuple[bool, str | None]:
        """Send via aiosmtplib SMTP.

        Returns (success, error_detail).
        SMTP does not confirm delivery — success means the server accepted the message.
        """
        try:
            import aiosmtplib  # optional dependency
        except ImportError:
            logger.error("aiosmtplib_not_installed", hint="pip install aiosmtplib")
            return False, "aiosmtplib not installed"

        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_address
        msg["To"] = to_email
        msg.attach(email.mime.text.MIMEText(html_content, "html", "utf-8"))

        try:
            await aiosmtplib.send(
                msg,
                hostname=host,
                port=port,
                username=user,
                password=password,
                use_tls=(port == 465),
                start_tls=(port == 587),
            )
            logger.info("smtp_send_ok", to=to_email, host=host)
            return True, None
        except Exception as exc:  # aiosmtplib.SMTPException and network errors
            logger.error("smtp_send_failed", to=to_email, error=str(exc))
            return False, str(exc)
