from __future__ import annotations

from pydantic import BaseModel


class EmailDraft(BaseModel):
    """Payload sent to N8N to create an Outlook draft."""

    to_email: str
    to_name: str
    subject: str
    body_html: str
    sender_email: str
    reply_to: str | None = None
    cc: list[str] = []
    bcc: list[str] = []
