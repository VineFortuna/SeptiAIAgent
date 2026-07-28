from __future__ import annotations

import os
import re

import requests


def _to_digits(phone: str) -> str:
    """Strip whatsapp:+1234567890 or +1234567890 down to digits only."""
    return re.sub(r"[^0-9]", "", phone)


def send_whatsapp_message(to: str, body: str, **_kwargs) -> bool:
    """Send a WhatsApp message via Meta Cloud API.

    Never raises — a send failure must not break the customer-facing webhook
    reply. Returns False (no-op) if the required env vars aren't set.
    """
    access_token = os.getenv("WHATSAPP_TOKEN", "").strip()
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()

    if not all([access_token, phone_number_id, to]):
        return False

    recipient = _to_digits(to)
    if not recipient:
        return False

    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            print(f"[META] Sent to +{recipient}")
            return True
        print(f"[META ERROR] {resp.status_code}: {resp.text[:200]}")
        return False
    except Exception as exc:
        print(f"[META ERROR] Failed to send to +{recipient}: {exc}")
        return False


def send_staff_notification(body: str, **_kwargs) -> bool:
    """Send a WhatsApp message to the configured staff number."""
    staff_number = os.getenv("STAFF_NOTIFICATION_PHONE", "").strip()
    if not staff_number:
        return False
    return send_whatsapp_message(staff_number, body)
