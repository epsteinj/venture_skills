"""N8N webhook client – triggers an Outlook draft creation workflow.

Expected N8N workflow setup:
  1. Webhook trigger node (POST, JSON body)
  2. Microsoft Outlook node → "Create Draft Message"

The webhook payload contract is defined by the EmailDraft model.
"""

from __future__ import annotations

import httpx

from cold_email_skill.models.email_draft import EmailDraft


class N8NClient:
    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url
        self._client = httpx.Client(timeout=30)

    def create_outlook_draft(self, draft: EmailDraft) -> dict:
        """POST the email draft payload to the N8N webhook.

        Expected webhook payload (JSON):
        {
            "to_email":      "jane@acme.com",
            "to_name":       "Jane Smith",
            "subject":       "Quick intro – ...",
            "body_html":     "<p>Hi Jane, ...</p>",
            "sender_email":  "you@yourcompany.com",
            "reply_to":      null,
            "cc":            [],
            "bcc":           []
        }

        The N8N workflow should map these fields to the Outlook
        "Create Draft Message" node.

        Returns the JSON response from N8N (typically includes
        {"success": true} on a 200).
        """
        resp = self._client.post(
            self._webhook_url,
            json=draft.model_dump(),
        )
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self._client.close()
