from __future__ import annotations

import os
from functools import wraps
from typing import Callable, TypeVar, Any

from dotenv import load_dotenv
from flask import Flask, Response, abort, jsonify, request
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from bot import ClassAssistant

load_dotenv()

app = Flask(__name__)
assistant = ClassAssistant()

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
        }
    )


@app.post("/whatsapp")
@validate_twilio_request
def whatsapp_webhook() -> Response:
    message = request.form.get("Body", "").strip()
    sender = request.form.get("From", "").replace("whatsapp:", "").strip()

    reply_text = assistant.reply(message=message, sender_phone=sender)

    response = MessagingResponse()
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
