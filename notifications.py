from __future__ import annotations

import os
from typing import Any


def send_whatsapp_message(to: str, body: str, *, client: Any = None) -> bool:
    """Send a WhatsApp message to an arbitrary number via Twilio.

    Never raises - a send failure must not break the customer-facing
    webhook reply. Returns False (no-op) if the required env vars aren't set.
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    from_number = os.getenv("TWILIO_WHATSAPP_FROM", "").strip()

    if not all([account_sid, auth_token, from_number, to]):
        return False

    try:
        if client is None:
            from twilio.rest import Client

            client = Client(account_sid, auth_token)

        client.messages.create(from_=from_number, to=to, body=body)
        return True

    except Exception:
        return False


def send_staff_notification(body: str, *, client: Any = None) -> bool:
    """Send a WhatsApp message to the configured staff number via Twilio."""
    staff_number = os.getenv("STAFF_NOTIFICATION_PHONE", "").strip()

    if not staff_number:
        return False

    return send_whatsapp_message(staff_number, body, client=client)
