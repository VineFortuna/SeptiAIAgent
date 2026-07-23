from __future__ import annotations

import os
import time
from datetime import datetime, timezone, timedelta
from functools import wraps
from threading import Thread
from typing import Callable, TypeVar, Any

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from flask import Flask, Response, abort, jsonify, request
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from bot import ClassAssistant
from notifications import send_whatsapp_message

load_dotenv()

app = Flask(__name__)

# MessageSid → received_at. Twilio retries on timeout/5xx; we drop duplicates
# that arrive within 10 minutes of the original.
_seen_message_sids: dict[str, datetime] = {}
_SID_TTL = timedelta(minutes=10)


def _is_duplicate_sid(sid: str) -> bool:
    """Return True if this MessageSid was already processed recently."""
    if not sid:
        return False
    now = datetime.now(timezone.utc)
    # Purge stale entries to keep the dict small
    expired = [k for k, ts in _seen_message_sids.items() if now - ts > _SID_TTL]
    for k in expired:
        del _seen_message_sids[k]
    if sid in _seen_message_sids:
        return True
    _seen_message_sids[sid] = now
    return False

if os.getenv("VALIDATE_TWILIO_SIGNATURE", "false").lower() != "true":
    import logging
    logging.getLogger(__name__).warning(
        "VALIDATE_TWILIO_SIGNATURE is disabled — anyone can send fake messages "
        "to this webhook. Set it to true before going live."
    )
assistant = ClassAssistant()

# Check for abandoned intakes every hour.
# In Flask debug mode the reloader spawns two processes; WERKZEUG_RUN_MAIN is
# only set in the actual serving child, so we use it to avoid double-starting
# the scheduler there. Outside debug mode (production / gunicorn) that env var
# is never set, so we fall back to starting unconditionally.
scheduler = BackgroundScheduler()
scheduler.add_job(assistant.send_abandoned_intake_nudges, "interval", hours=1)
scheduler.add_job(assistant.send_post_intake_nudges, "interval", hours=1)

_debug_mode = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true")
if not _debug_mode or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    scheduler.start()

F = TypeVar("F", bound=Callable[..., Any])


def require_admin_key(view: F) -> F:
    """Protect admin endpoints with a secret key from the ADMIN_API_KEY env var.

    If ADMIN_API_KEY is not set the endpoint is unrestricted (local dev only).
    In production, set ADMIN_API_KEY and pass it as the X-Admin-Key header.
    """
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        expected = os.getenv("ADMIN_API_KEY", "").strip()
        if expected:
            provided = request.headers.get("X-Admin-Key", "").strip()
            if not provided or provided != expected:
                return jsonify({"error": "Unauthorized"}), 401
        return view(*args, **kwargs)
    return wrapped  # type: ignore[return-value]


def validate_twilio_request(view: F) -> F:
    """Validate requests from Twilio when validation is enabled.

    During the very first local test, VALIDATE_TWILIO_SIGNATURE can be false.
    It should be true before this bot is deployed for real use.
    """

    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        enabled = os.getenv("VALIDATE_TWILIO_SIGNATURE", "false").lower() == "true"
        if not enabled:
            return view(*args, **kwargs)

        auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
        public_base_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

        if not auth_token or not public_base_url:
            app.logger.error(
                "Twilio validation is enabled, but TWILIO_AUTH_TOKEN or "
                "PUBLIC_BASE_URL is missing."
            )
            abort(500)

        signature = request.headers.get("X-Twilio-Signature", "")
        webhook_url = f"{public_base_url}{request.path}"
        validator = RequestValidator(auth_token)

        if not validator.validate(webhook_url, request.form, signature):
            abort(403)

        return view(*args, **kwargs)

    return wrapped  # type: ignore[return-value]


@app.get("/")
def health() -> Response:
    return jsonify(
        {
            "status": "ok",
            "service": "WhatsApp Class Assistant",
            "ai_enabled": assistant.ai_enabled,
        }
    )


@app.post("/whatsapp")
@validate_twilio_request
def whatsapp_webhook() -> Response:
    message_sid = request.form.get("MessageSid", "")
    if _is_duplicate_sid(message_sid):
        return Response(str(MessagingResponse()), status=200, mimetype="application/xml")

    message = request.form.get("Body", "").strip()
    sender = request.form.get("From", "").replace("whatsapp:", "").strip()
    num_media = int(request.form.get("NumMedia", "0"))

    response = MessagingResponse()

    # Voice notes, images, stickers — reply immediately regardless of business hours
    # since queuing an empty message and replying to it later is broken behavior.
    if not message and num_media > 0:
        sender_wa = f"whatsapp:{sender}"
        media_text = (
            "I can only read text messages right now, feel free to type your question 🙂\n\n"
            "Nu pot citi mesaje vocale sau imagini deocamdată, scrie-mi întrebarea 🙂"
        )
        Thread(
            target=send_whatsapp_message,
            args=(sender_wa, media_text),
            daemon=True,
        ).start()
        return Response(str(response), status=200, mimetype="application/xml")

    # Blank text with no media (accidental send) — silently no-op rather than
    # creating a spurious lead or returning a confused greeting.
    if not message:
        return Response(str(response), status=200, mimetype="application/xml")

    reply_parts = assistant.reply(message=message, sender_phone=sender)
    sender_wa = f"whatsapp:{sender}"

    def _send_all(parts: list[str], to: str) -> None:
        for i, part in enumerate(parts):
            time.sleep(1.2 if i == 0 else 2.5)
            send_whatsapp_message(to, part)

    Thread(target=_send_all, args=(reply_parts, sender_wa), daemon=True).start()

    # Return empty TwiML immediately so Twilio doesn't wait on us.
    return Response(str(response), status=200, mimetype="application/xml")


@app.get("/leads")
@require_admin_key
def leads_dashboard() -> Response:
    """Summary of all leads — who's enquired, where they are in the funnel."""
    leads = assistant.leads

    by_stage: dict[str, int] = {}
    lead_summaries = []

    for phone, lead in sorted(
        leads.items(),
        key=lambda x: x[1].get("updated_at") or x[1].get("created_at", ""),
        reverse=True,
    ):
        stage = lead.get("stage", "unknown")
        by_stage[stage] = by_stage.get(stage, 0) + 1

        lead_summaries.append({
            "phone": phone,
            "wa_link": f"https://wa.me/{phone.lstrip('+')}",
            "stage": stage,
            "country": lead.get("country") or "-",
            "child_age": lead.get("child_age") or "-",
            "timezone": lead.get("timezone") or "-",
            "child_language_pref": lead.get("child_language_pref") or "-",
            "fields_collected": len(lead.get("collected_fields", [])),
            "referral_source": lead.get("referral_source") or "-",
            "handed_off": lead.get("handed_off", False),
            "demo_completed": lead.get("demo_completed", False),
            "demo_outcome": lead.get("demo_outcome") or "-",
            "nudge_sent": lead.get("nudge_sent", False),
            "post_intake_nudge_sent": lead.get("post_intake_nudge_sent", False),
            "multi_child": lead.get("multi_child", False),
            "created_at": lead.get("created_at", "-"),
            "last_active": lead.get("updated_at") or lead.get("created_at", "-"),
        })

    return jsonify({
        "total": len(leads),
        "by_stage": by_stage,
        "leads": lead_summaries,
    })


@app.post("/mark-demo/<path:phone>")
@require_admin_key
def mark_demo(phone: str) -> Response:
    """Mark a lead's demo as completed so nudge jobs skip them.

    Accepts phone in any format (+14165550100, 14165550100, whatsapp:+14165550100).
    Optionally pass JSON body: {"outcome": "enrolled" | "no_show" | "considering"}
    """
    phone = phone.replace("whatsapp:", "").strip()
    if not phone.startswith("+"):
        phone = f"+{phone}"

    lead = assistant.leads.get(phone)
    if not lead:
        return jsonify({"error": f"No lead found for {phone}"}), 404

    payload = request.get_json(silent=True) or {}
    outcome = payload.get("outcome", "completed")

    lead["demo_completed"] = True
    lead["demo_outcome"] = outcome
    assistant._save_leads()  # type: ignore[attr-defined]

    return jsonify({"status": "ok", "phone": phone, "outcome": outcome})


@app.post("/reset-state")
@require_admin_key
def reset_state() -> Response:
    """Dev-only: wipe all leads and conversation history from memory and disk."""
    assistant.clear_state()
    return jsonify({"status": "ok", "message": "All leads and history cleared"})


@app.post("/test-message")
@require_admin_key
def test_message() -> Response:
    """Local-only helper so the bot can be tested before Twilio is connected."""
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    phone = str(payload.get("phone", "+14165550100")).strip()

    if not message:
        return jsonify({"error": "The 'message' field is required."}), 400

    parts = assistant.reply(message=message, sender_phone=phone)
    return jsonify({"reply": "\n\n".join(parts)})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
