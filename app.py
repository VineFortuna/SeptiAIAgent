from __future__ import annotations

import os
import time
from datetime import datetime, timezone, timedelta
from functools import wraps
from threading import Thread
from typing import Callable, TypeVar, Any

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request

from bot import ClassAssistant
from notifications import send_whatsapp_message

load_dotenv()

app = Flask(__name__)

# Message ID deduplication — Meta retries on timeout / 5xx; drop duplicates
# that arrive within 10 minutes of the original.
_seen_message_ids: dict[str, datetime] = {}
_MSG_TTL = timedelta(minutes=10)


def _is_duplicate_id(msg_id: str) -> bool:
    """Return True if this message ID was already processed recently."""
    if not msg_id:
        return False
    now = datetime.now(timezone.utc)
    expired = [k for k, ts in _seen_message_ids.items() if now - ts > _MSG_TTL]
    for k in expired:
        del _seen_message_ids[k]
    if msg_id in _seen_message_ids:
        return True
    _seen_message_ids[msg_id] = now
    return False


assistant = ClassAssistant()

scheduler = BackgroundScheduler()
scheduler.add_job(assistant.send_abandoned_intake_nudges, "interval", hours=1)
scheduler.add_job(assistant.send_post_intake_nudges, "interval", hours=1)
scheduler.add_job(assistant.send_thinking_it_over_nudges, "interval", hours=6)

_debug_mode = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true")
if not _debug_mode or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    scheduler.start()

F = TypeVar("F", bound=Callable[..., Any])


def require_admin_key(view: F) -> F:
    """Protect admin endpoints with a secret key from the ADMIN_API_KEY env var."""
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        expected = os.getenv("ADMIN_API_KEY", "").strip()
        if expected:
            provided = request.headers.get("X-Admin-Key", "").strip()
            if not provided or provided != expected:
                return jsonify({"error": "Unauthorized"}), 401
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


@app.get("/whatsapp")
def verify_webhook() -> Response:
    """Meta sends a GET request to verify the webhook URL before activating it."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "").strip()

    if mode == "subscribe" and token == verify_token:
        return Response(challenge, status=200, mimetype="text/plain")
    return Response("Forbidden", status=403)


@app.post("/whatsapp")
def whatsapp_webhook() -> Response:
    """Receive incoming WhatsApp messages from Meta Cloud API."""
    data = request.get_json(silent=True) or {}

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})

            # Status updates (delivered, read) arrive on the same webhook — ignore them
            if not value.get("messages"):
                continue

            for msg in value["messages"]:
                msg_id = msg.get("id", "")
                if _is_duplicate_id(msg_id):
                    continue

                sender = msg.get("from", "")  # digits only, no + prefix from Meta
                if not sender:
                    continue

                sender_phone = f"+{sender}"
                msg_type = msg.get("type", "")

                if msg_type != "text":
                    # Voice notes, images, stickers — reply immediately
                    media_text = (
                        "I can only read text messages right now, feel free to type your question 🙂\n\n"
                        "Nu pot citi mesaje vocale sau imagini deocamdată, scrie-mi întrebarea 🙂"
                    )
                    Thread(
                        target=send_whatsapp_message,
                        args=(sender_phone, media_text),
                        daemon=True,
                    ).start()
                    continue

                message = msg.get("text", {}).get("body", "").strip()
                if not message:
                    continue

                reply_parts = assistant.reply(message=message, sender_phone=sender_phone)

                def _send_all(parts: list[str], to: str) -> None:
                    for i, part in enumerate(parts):
                        time.sleep(1.2 if i == 0 else 2.5)
                        send_whatsapp_message(to, part)

                Thread(target=_send_all, args=(reply_parts, sender_phone), daemon=True).start()

    return jsonify({"status": "ok"}), 200


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
            "thinking_it_over": lead.get("thinking_it_over", False),
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
    """Mark a lead's demo as completed so nudge jobs skip them."""
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
    """Local-only helper so the bot can be tested before WhatsApp is connected."""
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
