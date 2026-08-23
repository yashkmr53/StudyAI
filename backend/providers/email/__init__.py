"""Email providers (Phase 11).

Implements EmailProvider protocol for sending transactional emails.
Supports Mailpit (local development), SMTP (production), and console (testing).
"""
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import requests

from providers.base import EmailProvider

logger = logging.getLogger(__name__)


class MailpitEmailProvider:
    """Mailpit local email testing provider.
    
    Captures emails locally for development/testing without sending real emails.
    Mailpit provides a web UI at http://localhost:8025 to view captured emails.
    
    Environment variables:
        MAILPIT_HOST: Mailpit SMTP host (default: localhost)
        MAILPIT_PORT: Mailpit SMTP port (default: 1025)
        MAILPIT_API_URL: Mailpit API URL (default: http://localhost:8025)
        EMAIL_FROM: Default from email (default: noreply@studyai.local)
    """
    
    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        api_url: str | None = None,
        from_email: str | None = None,
        fail: bool = False,
        name: str = "mailpit",
    ):
        self.name = name
        self.fail = fail
        self.host = host or os.environ.get("MAILPIT_HOST", "localhost")
        self.port = port or int(os.environ.get("MAILPIT_PORT", "1025"))
        self.api_url = api_url or os.environ.get("MAILPIT_API_URL", "http://localhost:8025")
        self.from_email = from_email or os.environ.get("EMAIL_FROM", "noreply@studyai.local")
        
        self._check_mailpit()
        logger.info("Mailpit email provider initialized (host=%s:%d, api=%s)", self.host, self.port, self.api_url)
    
    def _check_mailpit(self) -> None:
        """Verify Mailpit is reachable."""
        try:
            resp = requests.get(f"{self.api_url}/api/v1/messages", timeout=5)
            resp.raise_for_status()
            logger.info("Mailpit API reachable")
        except requests.exceptions.ConnectionError:
            logger.warning("Cannot connect to Mailpit API at %s", self.api_url)
        except Exception as e:
            logger.warning("Mailpit health check failed: %s", e)
    
    def send_email(
        self,
        *,
        to: list[str],
        subject: str,
        body_text: str,
        body_html: str | None = None,
        from_email: str | None = None,
    ) -> None:
        """Send email via Mailpit SMTP."""
        if self.fail:
            raise RuntimeError(f"{self.name}: simulated provider failure")
        
        from_addr = from_email or self.from_email
        
        # Create message
        if body_html:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body_text, "plain"))
            msg.attach(MIMEText(body_html, "html"))
        else:
            msg = MIMEText(body_text, "plain")
        
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = ", ".join(to)
        
        try:
            with smtplib.SMTP(self.host, self.port) as server:
                server.sendmail(from_addr, to, msg.as_string())
            logger.info("Email sent via Mailpit to %s", to)
        except Exception as e:
            logger.exception("Failed to send email via Mailpit")
            raise RuntimeError(f"Failed to send email via Mailpit: {e}") from e
    
    def send_password_reset_email(
        self,
        *,
        to: str,
        reset_url: str,
        user_name: str,
    ) -> None:
        """Send password reset email."""
        subject = "Reset your StudyAI password"
        body_text = (
            f"Hi {user_name},\n\n"
            f"You requested a password reset. Click the link below to set a new password:\n\n"
            f"{reset_url}\n\n"
            f"This link expires in 1 hour. If you didn't request this, please ignore this email.\n\n"
            f"— The StudyAI Team"
        )
        body_html = (
            f"<p>Hi {user_name},</p>"
            f"<p>You requested a password reset. Click the button below to set a new password:</p>"
            f"<p><a href='{reset_url}' style='display: inline-block; padding: 12px 24px; "
            f"background-color: #2563eb; color: white; text-decoration: none; border-radius: 4px;'>"
            f"Reset Password</a></p>"
            f"<p>This link expires in 1 hour. If you didn't request this, please ignore this email.</p>"
            f"<p>— The StudyAI Team</p>"
        )
        self.send_email(to=[to], subject=subject, body_text=body_text, body_html=body_html)
    
    def get_captured_emails(self) -> list[dict]:
        """Get all captured emails from Mailpit API (for testing)."""
        try:
            resp = requests.get(f"{self.api_url}/api/v1/messages", timeout=5)
            resp.raise_for_status()
            return resp.json().get("messages", [])
        except Exception as e:
            logger.warning("Failed to fetch captured emails: %s", e)
            return []


class SMTPEmailProvider:
    """Production SMTP email provider.
    
    Sends real emails via SMTP server.
    
    Environment variables:
        SMTP_HOST: SMTP server host
        SMTP_PORT: SMTP server port (default: 587)
        SMTP_USERNAME: SMTP username
        SMTP_PASSWORD: SMTP password
        SMTP_USE_TLS: Use TLS (default: true)
        SMTP_USE_SSL: Use SSL (default: false)
        EMAIL_FROM: Default from email
    """
    
    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        use_ssl: bool = False,
        from_email: str | None = None,
        fail: bool = False,
        name: str = "smtp",
    ):
        self.name = name
        self.fail = fail
        self.host = host or os.environ.get("SMTP_HOST")
        self.port = port or int(os.environ.get("SMTP_PORT", "587"))
        self.username = username or os.environ.get("SMTP_USERNAME")
        self.password = password or os.environ.get("SMTP_PASSWORD")
        self.use_tls = use_tls if use_tls is not None else os.environ.get("SMTP_USE_TLS", "true").lower() == "true"
        self.use_ssl = use_ssl if use_ssl is not None else os.environ.get("SMTP_USE_SSL", "false").lower() == "true"
        self.from_email = from_email or os.environ.get("EMAIL_FROM", "noreply@studyai.com")
        
        if not self.host:
            logger.warning("SMTP_HOST not configured; SMTPEmailProvider will not work")
        
        logger.info("SMTP email provider initialized (host=%s:%d, tls=%s, ssl=%s)",
                    self.host, self.port, self.use_tls, self.use_ssl)
    
    def _get_connection(self):
        """Get SMTP connection."""
        if self.use_ssl:
            server = smtplib.SMTP_SSL(self.host, self.port)
        else:
            server = smtplib.SMTP(self.host, self.port)
            if self.use_tls:
                server.starttls()
        
        if self.username and self.password:
            server.login(self.username, self.password)
        
        return server
    
    def send_email(
        self,
        *,
        to: list[str],
        subject: str,
        body_text: str,
        body_html: str | None = None,
        from_email: str | None = None,
    ) -> None:
        """Send email via SMTP."""
        if self.fail:
            raise RuntimeError(f"{self.name}: simulated provider failure")
        
        if not self.host:
            raise RuntimeError("SMTP_HOST not configured")
        
        from_addr = from_email or self.from_email
        
        # Create message
        if body_html:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body_text, "plain"))
            msg.attach(MIMEText(body_html, "html"))
        else:
            msg = MIMEText(body_text, "plain")
        
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = ", ".join(to)
        
        try:
            with self._get_connection() as server:
                server.sendmail(from_addr, to, msg.as_string())
            logger.info("Email sent via SMTP to %s", to)
        except Exception as e:
            logger.exception("Failed to send email via SMTP")
            raise RuntimeError(f"Failed to send email via SMTP: {e}") from e
    
    def send_password_reset_email(
        self,
        *,
        to: str,
        reset_url: str,
        user_name: str,
    ) -> None:
        """Send password reset email."""
        subject = "Reset your StudyAI password"
        body_text = (
            f"Hi {user_name},\n\n"
            f"You requested a password reset. Click the link below to set a new password:\n\n"
            f"{reset_url}\n\n"
            f"This link expires in 1 hour. If you didn't request this, please ignore this email.\n\n"
            f"— The StudyAI Team"
        )
        body_html = (
            f"<p>Hi {user_name},</p>"
            f"<p>You requested a password reset. Click the button below to set a new password:</p>"
            f"<p><a href='{reset_url}' style='display: inline-block; padding: 12px 24px; "
            f"background-color: #2563eb; color: white; text-decoration: none; border-radius: 4px;'>"
            f"Reset Password</a></p>"
            f"<p>This link expires in 1 hour. If you didn't request this, please ignore this email.</p>"
            f"<p>— The StudyAI Team</p>"
        )
        self.send_email(to=[to], subject=subject, body_text=body_text, body_html=body_html)


class ConsoleEmailProvider:
    """Console email provider for testing.
    
    Prints emails to stdout instead of sending them.
    Useful for tests and local development without Mailpit.
    """
    
    def __init__(self, *, fail: bool = False, name: str = "console"):
        self.name = name
        self.fail = fail
        self._sent_emails: list[dict] = []
    
    def send_email(
        self,
        *,
        to: list[str],
        subject: str,
        body_text: str,
        body_html: str | None = None,
        from_email: str | None = None,
    ) -> None:
        if self.fail:
            raise RuntimeError(f"{self.name}: simulated provider failure")
        
        email = {
            "to": to,
            "subject": subject,
            "body_text": body_text,
            "body_html": body_html,
            "from_email": from_email,
        }
        self._sent_emails.append(email)
        
        print(f"\n{'='*60}")
        print(f"EMAIL (console backend)")
        print(f"{'='*60}")
        print(f"To: {', '.join(to)}")
        print(f"From: {from_email or 'noreply@studyai.local'}")
        print(f"Subject: {subject}")
        print(f"Body: {body_text[:500]}")
        if body_html:
            print(f"HTML: {body_html[:500]}")
        print(f"{'='*60}\n")
    
    def send_password_reset_email(
        self,
        *,
        to: str,
        reset_url: str,
        user_name: str,
    ) -> None:
        subject = "Reset your StudyAI password"
        body_text = (
            f"Hi {user_name},\n\n"
            f"You requested a password reset. Click the link below to set a new password:\n\n"
            f"{reset_url}\n\n"
            f"This link expires in 1 hour. If you didn't request this, please ignore this email.\n\n"
            f"— The StudyAI Team"
        )
        self.send_email(to=[to], subject=subject, body_text=body_text)
    
    def get_sent_emails(self) -> list[dict]:
        """Get all sent emails (for testing)."""
        return self._sent_emails
    
    def clear_sent_emails(self) -> None:
        """Clear sent emails list."""
        self._sent_emails.clear()