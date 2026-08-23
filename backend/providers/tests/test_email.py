"""Email delivery tests (Phase 11)."""
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings

from providers.email import (
    MailpitEmailProvider,
    SMTPEmailProvider,
    ConsoleEmailProvider,
)
from providers.base import EmailProvider


class TestConsoleEmailProvider(TestCase):
    """Test console email provider (for testing)."""

    def test_send_email(self):
        """Should capture emails in memory."""
        provider = ConsoleEmailProvider()
        
        provider.send_email(
            to=["user@example.com"],
            subject="Test Subject",
            body_text="Hello World",
            body_html="<p>Hello World</p>",
            from_email="sender@example.com",
        )
        
        emails = provider.get_sent_emails()
        assert len(emails) == 1
        assert emails[0]["to"] == ["user@example.com"]
        assert emails[0]["subject"] == "Test Subject"
        assert emails[0]["body_text"] == "Hello World"
        assert emails[0]["body_html"] == "<p>Hello World</p>"
        assert emails[0]["from_email"] == "sender@example.com"

    def test_send_password_reset(self):
        """Should send password reset email."""
        provider = ConsoleEmailProvider()
        
        provider.send_password_reset_email(
            to="user@example.com",
            reset_url="https://app.example.com/reset?token=abc123",
            user_name="John Doe",
        )
        
        emails = provider.get_sent_emails()
        assert len(emails) == 1
        assert emails[0]["to"] == ["user@example.com"]
        assert "Reset your StudyAI password" in emails[0]["subject"]
        assert "John Doe" in emails[0]["body_text"]
        assert "https://app.example.com/reset?token=abc123" in emails[0]["body_text"]

    def test_clear_sent_emails(self):
        """Should clear captured emails."""
        provider = ConsoleEmailProvider()
        
        provider.send_email(to=["a@b.com"], subject="Test", body_text="Test")
        assert len(provider.get_sent_emails()) == 1
        
        provider.clear_sent_emails()
        assert len(provider.get_sent_emails()) == 0

    def test_implements_email_provider(self):
        """Should implement EmailProvider protocol."""
        provider = ConsoleEmailProvider()
        assert isinstance(provider, EmailProvider)


class TestMailpitEmailProvider(TestCase):
    """Test Mailpit email provider."""

    @patch("providers.email.requests.get")
    def test_initialization(self, mock_get):
        """Should initialize and check Mailpit API."""
        mock_get.return_value.json.return_value = {"messages": []}
        mock_get.return_value.raise_for_status = MagicMock()
        
        provider = MailpitEmailProvider(
            host="mailpit",
            port=1025,
            api_url="http://mailpit:8025",
            from_email="noreply@test.local",
        )
        
        assert provider.name == "mailpit"
        assert provider.host == "mailpit"
        assert provider.port == 1025
        mock_get.assert_called_once_with("http://mailpit:8025/api/v1/messages", timeout=5)

    @patch("providers.email.requests.get")
    @patch("providers.email.smtplib.SMTP")
    def test_send_email(self, mock_smtp_class, mock_get):
        """Should send email via Mailpit SMTP."""
        mock_get.return_value.json.return_value = {"messages": []}
        mock_get.return_value.raise_for_status = MagicMock()
        
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp
        
        provider = MailpitEmailProvider(host="mailpit", port=1025)
        
        provider.send_email(
            to=["user@example.com"],
            subject="Test",
            body_text="Hello",
        )
        
        mock_smtp_class.assert_called_once_with("mailpit", 1025)
        mock_smtp.sendmail.assert_called_once()
        
        # Check email content
        call_args = mock_smtp.sendmail.call_args
        assert call_args[0][0] == "noreply@studyai.local"  # from
        assert call_args[0][1] == ["user@example.com"]  # to
        assert "Subject: Test" in call_args[0][2]  # message

    @patch("providers.email.requests.get")
    @patch("providers.email.smtplib.SMTP")
    def test_send_html_email(self, mock_smtp_class, mock_get):
        """Should send multipart HTML email."""
        mock_get.return_value.json.return_value = {"messages": []}
        mock_get.return_value.raise_for_status = MagicMock()
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp
        
        provider = MailpitEmailProvider()
        provider.send_email(
            to=["user@example.com"],
            subject="Test",
            body_text="Text version",
            body_html="<p>HTML version</p>",
        )
        
        call_args = mock_smtp.sendmail.call_args
        message = call_args[0][2]
        assert "Content-Type: multipart/alternative" in message
        assert "Text version" in message
        assert "<p>HTML version</p>" in message

    @patch("providers.email.requests.get")
    @patch("providers.email.requests.get")
    def test_get_captured_emails(self, mock_get_messages, mock_get_init):
        """Should retrieve captured emails from Mailpit API."""
        mock_get_init.return_value.json.return_value = {"messages": []}
        mock_get_init.return_value.raise_for_status = MagicMock()
        
        mock_get_messages.return_value.json.return_value = {
            "messages": [
                {"ID": "1", "Subject": "Test 1", "From": "a@b.com", "To": ["c@d.com"]},
                {"ID": "2", "Subject": "Test 2", "From": "e@f.com", "To": ["g@h.com"]},
            ]
        }
        mock_get_messages.return_value.raise_for_status = MagicMock()
        
        provider = MailpitEmailProvider()
        emails = provider.get_captured_emails()
        
        assert len(emails) == 2
        assert emails[0]["Subject"] == "Test 1"
        assert emails[1]["Subject"] == "Test 2"

    def test_implements_email_provider(self):
        """Should implement EmailProvider protocol."""
        with patch("providers.email.requests.get") as mock_get:
            mock_get.return_value.json.return_value = {"messages": []}
            mock_get.return_value.raise_for_status = MagicMock()
            
            provider = MailpitEmailProvider()
            assert isinstance(provider, EmailProvider)


class TestSMTPEmailProvider(TestCase):
    """Test production SMTP email provider."""

    def test_initialization_missing_host_warns(self):
        """Should warn when SMTP_HOST not configured."""
        with self.assertLogs(level="WARNING") as cm:
            provider = SMTPEmailProvider(host=None)
        
        assert any("SMTP_HOST not configured" in msg for msg in cm.output)

    @patch("providers.email.smtplib.SMTP")
    def test_send_email_tls(self, mock_smtp_class):
        """Should send email with TLS."""
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp
        
        provider = SMTPEmailProvider(
            host="smtp.example.com",
            port=587,
            username="user",
            password="pass",
            use_tls=True,
            use_ssl=False,
        )
        
        provider.send_email(
            to=["user@example.com"],
            subject="Test",
            body_text="Hello",
        )
        
        mock_smtp_class.assert_called_once_with("smtp.example.com", 587)
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("user", "pass")
        mock_smtp.sendmail.assert_called_once()

    @patch("providers.email.smtplib.SMTP_SSL")
    def test_send_email_ssl(self, mock_smtp_ssl_class):
        """Should send email with SSL."""
        mock_smtp = MagicMock()
        mock_smtp_ssl_class.return_value.__enter__.return_value = mock_smtp
        
        provider = SMTPEmailProvider(
            host="smtp.example.com",
            port=465,
            username="user",
            password="pass",
            use_tls=False,
            use_ssl=True,
        )
        
        provider.send_email(
            to=["user@example.com"],
            subject="Test",
            body_text="Hello",
        )
        
        mock_smtp_ssl_class.assert_called_once_with("smtp.example.com", 465)
        mock_smtp.login.assert_called_once_with("user", "pass")
        # No starttls for SSL
        assert not hasattr(mock_smtp, 'starttls') or not mock_smtp.starttls.called

    @patch("providers.email.smtplib.SMTP")
    def test_send_without_auth(self, mock_smtp_class):
        """Should work without authentication."""
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp
        
        provider = SMTPEmailProvider(
            host="smtp.example.com",
            port=25,
            username=None,
            password=None,
        )
        
        provider.send_email(
            to=["user@example.com"],
            subject="Test",
            body_text="Hello",
        )
        
        mock_smtp.login.assert_not_called()

    def test_missing_host_raises_on_send(self):
        """Should raise error when trying to send without host."""
        provider = SMTPEmailProvider(host=None)
        
        with self.assertRaises(RuntimeError) as cm:
            provider.send_email(
                to=["user@example.com"],
                subject="Test",
                body_text="Hello",
            )
        
        assert "SMTP_HOST not configured" in str(cm.exception)

    def test_implements_email_provider(self):
        """Should implement EmailProvider protocol."""
        provider = SMTPEmailProvider(host="smtp.example.com")
        assert isinstance(provider, EmailProvider)


class TestEmailProviderInterface(TestCase):
    """Test EmailProvider protocol compliance."""

    def test_all_providers_implement_interface(self):
        """All email providers should implement the protocol."""
        console = ConsoleEmailProvider()
        
        with patch("providers.email.requests.get") as mock_get:
            mock_get.return_value.json.return_value = {"messages": []}
            mock_get.return_value.raise_for_status = MagicMock()
            mailpit = MailpitEmailProvider()
        
        smtp = SMTPEmailProvider(host="smtp.example.com")
        
        for provider in [console, mailpit, smtp]:
            assert isinstance(provider, EmailProvider)
            assert hasattr(provider, "send_email")
            assert hasattr(provider, "send_password_reset_email")
            assert callable(provider.send_email)
            assert callable(provider.send_password_reset_email)

    def test_send_password_reset_signature(self):
        """All providers should accept same send_password_reset_email signature."""
        console = ConsoleEmailProvider()
        
        with patch("providers.email.requests.get") as mock_get:
            mock_get.return_value.json.return_value = {"messages": []}
            mock_get.return_value.raise_for_status = MagicMock()
            mailpit = MailpitEmailProvider()
        
        smtp = SMTPEmailProvider(host="smtp.example.com")
        
        for provider in [console, mailpit, smtp]:
            # Should not raise TypeError for correct signature
            try:
                provider.send_password_reset_email(
                    to="user@example.com",
                    reset_url="https://example.com/reset",
                    user_name="Test User",
                )
            except Exception as e:
                # May fail for other reasons (no SMTP connection), but not signature
                assert not isinstance(e, TypeError)