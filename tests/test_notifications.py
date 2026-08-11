from unittest.mock import patch, MagicMock

from bot import REQUIRED_INTAKE_FIELDS
from conftest import make_mock_client
from notifications import send_staff_notification, send_whatsapp_message


def test_notification_sends_via_meta_api(monkeypatch) -> None:
    monkeypatch.setenv("WHATSAPP_TOKEN", "fake-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456789")
    monkeypatch.setenv("STAFF_NOTIFICATION_PHONE", "+40700000000")

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("notifications.requests.post", return_value=mock_response) as mock_post:
        result = send_staff_notification("test body")

    assert result is True
    call_kwargs = mock_post.call_args
    payload = call_kwargs.kwargs["json"]
    assert payload["text"]["body"] == "test body"
    assert payload["to"] == "40700000000"


def test_notification_noop_when_unconfigured(monkeypatch) -> None:
    monkeypatch.delenv("WHATSAPP_TOKEN", raising=False)
    monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)
    monkeypatch.delenv("STAFF_NOTIFICATION_PHONE", raising=False)

    result = send_staff_notification("test body")

    assert result is False


def test_intake_completion_triggers_injected_notifier(bot) -> None:
    bot.ai_enabled = True
    sent: list[str] = []
    bot.notifier = lambda msg: sent.append(msg) or True

    result = {
        "reply": "All set, thanks!",
        "lang": "en",
        "wants_human": False,
        "thinking_it_over": False,
        "complete": True,
        "multiple_children": False,
        "demo_interest": True,
    }
    for field in REQUIRED_INTAKE_FIELDS:
        result.setdefault(field, "value")
    bot.client = make_mock_client("intake", result)

    phone = "+40712345678"
    bot.reply("yes", phone)   # demo_interest true, complete=true → triggers notification

    assert len(sent) == 1
    assert phone in sent[0]
