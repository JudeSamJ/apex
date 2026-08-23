import os
import logging
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage

from app.secrets.provider import get_secret

logger = logging.getLogger(__name__)


class EmailClient(ABC):
    @abstractmethod
    def send(self, to: str, subject: str, body: str) -> None:
        ...


class MockEmailClient(EmailClient):
    """Logs the email instead of sending it — sandbox/demo/test default."""

    def send(self, to: str, subject: str, body: str) -> None:
        logger.info(f"[mock email] to={to} subject={subject!r} body={body!r}")


class SMTPEmailClient(EmailClient):
    """Real email delivery via SMTP (SendGrid, Postmark, SES, or any SMTP relay
    all speak this protocol, so one client covers them)."""

    def __init__(self):
        self.host = os.getenv("SMTP_HOST")
        self.port = int(os.getenv("SMTP_PORT", "587"))
        self.username = get_secret("SMTP_USERNAME")
        self.password = get_secret("SMTP_PASSWORD")
        self.from_email = os.getenv("SMTP_FROM_EMAIL", self.username or "")

        if not self.host:
            raise ValueError("SMTP_HOST environment variable must be set")

    def send(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self.from_email
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
            smtp.starttls()
            if self.username and self.password:
                smtp.login(self.username, self.password)
            smtp.send_message(message)

        logger.info(f"Sent email to={to} subject={subject!r} via SMTP {self.host}")


def get_email_client() -> EmailClient:
    """Factory function to get the appropriate email client."""
    use_real = os.getenv("USE_REAL_EMAIL", "False").lower() in ["true", "1"]

    if use_real:
        return SMTPEmailClient()
    else:
        return MockEmailClient()
