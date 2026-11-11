"""Sends the one-time code for a duplicate name.

SMTP is configured with environment variables. DEMO_EMAIL_OVERRIDE sends
every code to one demo inbox instead of the roster address. With no SMTP
settings the mailer is in demo mode: nothing is sent, and the lecturer
dashboard shows the code under the label "מצב הדגמה – המייל לא נשלח".
"""

from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

DEMO_LABEL = "מצב הדגמה – המייל לא נשלח"


@dataclass
class SendResult:
    sent: bool
    demo: bool
    error: str = ""


class Mailer:
    def __init__(self, settings, smtp_factory=None):
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.user = settings.smtp_user
        self.password = settings.smtp_password
        self.sender = settings.smtp_from
        self.override = settings.demo_email_override
        self._factory = smtp_factory
        self.outbox_count = 0

    @property
    def configured(self) -> bool:
        return bool(self.host and self.sender)

    def recipient(self, roster_email: str) -> str:
        return self.override or roster_email

    def send_code(self, roster_email: str, display: str, course: str, code: str) -> SendResult:
        if not self.configured:
            return SendResult(sent=False, demo=True)
        to = self.recipient(roster_email)
        if not to:
            return SendResult(sent=False, demo=True, error="no_address")
        message = EmailMessage()
        message["Subject"] = f"ZooMoodle – קוד אימות לנוכחות ({course})"
        message["From"] = self.sender
        message["To"] = to
        message.set_content(
            f"שלום {display},\n\n"
            f"שני מכשירים בכיתה בחרו את השם שלך. כדי לאשר שזה אתה, הקלד באתר את הקוד:\n\n"
            f"{code}\n\nהקוד תקף ל־5 דקות ולשימוש אחד. אם זה לא אתה, אפשר להתעלם מהמייל.\n"
        )
        try:
            if self._factory is not None:
                smtp = self._factory(self.host, self.port)
            elif self.port == 465:
                smtp = smtplib.SMTP_SSL(self.host, self.port, context=ssl.create_default_context(), timeout=10)
            else:
                smtp = smtplib.SMTP(self.host, self.port, timeout=10)
            with smtp:
                if self._factory is None and self.port != 465:
                    smtp.starttls(context=ssl.create_default_context())
                if self.user:
                    smtp.login(self.user, self.password)
                smtp.send_message(message)
        except Exception as exc:  # never include the password or code in the error
            return SendResult(sent=False, demo=False, error=type(exc).__name__)
        self.outbox_count += 1
        return SendResult(sent=True, demo=False)
