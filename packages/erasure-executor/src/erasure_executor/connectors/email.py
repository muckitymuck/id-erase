from __future__ import annotations

import email as email_lib
import imaplib
import logging
import re
import smtplib
import time
from dataclasses import dataclass
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    message_id: str
    from_addr: str
    subject: str
    body: str
    html: str | None
    received_at: str
    links: list[str]


@dataclass
class EmailConfig:
    address: str
    imap_host: str
    imap_port: int
    smtp_host: str
    smtp_port: int
    password: str
    alternative_addresses: list[str]


class EmailConnector:
    """IMAP/SMTP client for the agent's dedicated email."""

    def __init__(self, config: EmailConfig):
        self._config = config

    def send(self, to: str, subject: str, body: str,
             from_addr: str | None = None) -> dict:
        """Send an email from the agent's address."""
        sender = from_addr or self._config.address
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to

        with smtplib.SMTP(self._config.smtp_host, self._config.smtp_port) as smtp:
            if self._config.smtp_port != 25:
                smtp.starttls()
            if self._config.password:
                smtp.login(self._config.address, self._config.password)
            smtp.send_message(msg)

        logger.info("email.sent to=%s subject=%s", to, subject)
        return {"status": "sent", "to": to, "subject": subject}

    def check_inbox(
        self,
        from_filter: str | None = None,
        subject_filter: str | None = None,
        wait_minutes: int = 0,
        poll_interval_seconds: int = 30,
    ) -> list[EmailMessage]:
        """Poll inbox for matching emails."""
        deadline = time.time() + (wait_minutes * 60)

        while True:
            results = self._search_inbox(from_filter, subject_filter)
            if results:
                return results
            if time.time() >= deadline:
                return []
            logger.info("email.polling wait_remaining=%.0fs", deadline - time.time())
            time.sleep(poll_interval_seconds)

    def _search_inbox(
        self, from_filter: str | None, subject_filter: str | None
    ) -> list[EmailMessage]:
        try:
            with imaplib.IMAP4_SSL(self._config.imap_host, self._config.imap_port) as imap:
                imap.login(self._config.address, self._config.password)
                imap.select("INBOX")

                criteria = []
                if from_filter:
                    criteria.append(f'FROM "{from_filter}"')
                if subject_filter:
                    criteria.append(f'SUBJECT "{subject_filter}"')

                search_str = " ".join(criteria) if criteria else "ALL"
                _, message_ids = imap.search(None, search_str)

                messages = []
                for mid in message_ids[0].split():
                    if not mid:
                        continue
                    _, data = imap.fetch(mid, "(RFC822)")
                    raw = email_lib.message_from_bytes(data[0][1])
                    body = self._get_body(raw)
                    html = self._get_html(raw)
                    text_for_links = body + (html or "")
                    links = self._extract_links(text_for_links)

                    messages.append(EmailMessage(
                        message_id=raw["Message-ID"] or "",
                        from_addr=raw["From"] or "",
                        subject=raw["Subject"] or "",
                        body=body,
                        html=html,
                        received_at=raw["Date"] or "",
                        links=links,
                    ))

                return messages
        except Exception:
            logger.exception("email.search_error")
            return []

    @staticmethod
    def _get_body(msg) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode("utf-8", errors="replace")
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode("utf-8", errors="replace")
        return ""

    @staticmethod
    def _get_html(msg) -> str | None:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode("utf-8", errors="replace")
        return None

    @staticmethod
    def _extract_links(text: str) -> list[str]:
        return re.findall(r"https?://[^\s<>\"']+", text)
