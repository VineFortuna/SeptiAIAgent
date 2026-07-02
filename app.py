from __future__ import annotations

import os
from functools import wraps
from typing import Callable, TypeVar, Any

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from flask import Flask, Response, abort, jsonify, request
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from bot import ClassAssistant, is_within_business_hours

load_dotenv()

app = Flask(__name__)
assistant = ClassAssistant()

# Catches up on any off-hours messages a few minutes after 7am Eastern hits,
# and otherwise just no-ops outside business hours. This file runs with
# debug=True below, which spawns a second "watcher" copy of this whole module
# under Flask's auto-reloader - WERKZEUG_RUN_MAIN is only set in the actual
# serving process, so this avoids starting two schedulers (which could double
# send a customer's deferred reply).
scheduler = BackgroundScheduler()
scheduler.add_job(assistant.process_pending_messages, "interval", minutes=10)

if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    scheduler.start()

F = TypeVar("F", bound=Callable[..., Any])


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
            "business_hours_open": is_within_business_hours(),
            "pending_messages": sum(len(v) for v in assistant.pending.values()),
        }
    )


@app.post("/whatsapp")
@validate_twilio_request
def whatsapp_webhook() -> Response:
    message = request.form.get("Body", "").strip()
    sender = request.form.get("From", "").replace("whatsapp:", "").strip()
    num_media = int(request.form.get("NumMedia", "0"))

    response = MessagingResponse()

    # Voice notes, images, stickers — reply immediately regardless of business hours
    # since queuing an empty message and replying to it later is broken behavior.
    if not message and num_media > 0:
        response.message(
            "I can only read text messages right now — feel free to type your question 🙂\n\n"
            "Nu pot citi mesaje vocale sau imagini deocamdată — scrie-mi întrebarea 🙂"
        )
        return Response(str(response), status=200, mimetype="application/xml")

    # Blank text with no media (accidental send) — silently no-op rather than
    # creating a spurious lead or returning a confused greeting.
    if not message:
        return Response(str(response), status=200, mimetype="application/xml")

    if not is_within_business_hours():
        assistant.queue_message(message, sender)
        return Response(str(response), status=200, mimetype="application/xml")

    reply_text = assistant.reply(message=message, sender_phone=sender)
    response.message(reply_text)
    return Response(str(response), status=200, mimetype="application/xml")


@app.post("/test-message")
def test_message() -> Response:
    """Local-only helper so the bot can be tested before Twilio is connected."""
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    phone = str(payload.get("phone", "+14165550100")).strip()

    if not message:
        return jsonify({"error": "The 'message' field is required."}), 400

    return jsonify({"reply": assistant.reply(message=message, sender_phone=phone)})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
