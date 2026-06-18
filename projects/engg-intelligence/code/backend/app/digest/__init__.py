"""Weekly digest generation and sending package.

Exposed entry points:
  - DigestGenerator  — renders role-scoped HTML from compiled MJML templates
  - DigestSender     — delivers rendered HTML via SendGrid or SMTP fallback

Spec §8 M7.
"""
from app.digest.generator import DigestGenerator
from app.digest.sender import DigestSender

__all__ = ["DigestGenerator", "DigestSender"]
