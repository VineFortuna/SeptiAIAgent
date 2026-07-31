from unittest.mock import patch, MagicMock

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
    sent: list[str] = []
    bot.notifier = sent.append

    phone = "+40712345678"
    bot.reply("Hi", phone)
    bot.reply("I want to sign up", phone)
    bot.reply("John", phone)
    bot.reply("Emma", phone)
    bot.reply("Romanian", phone)
    bot.reply("GMT+2", phone)
    bot.reply("7 years old", phone)
    bot.reply("No, never played", phone)
    bot.reply("Weekday evenings", phone)
    bot.reply("After 3:30pm", phone)
    bot.reply("Exploratori", phone)
    bot.reply("No extra notes", phone)
    bot.reply("TikTok", phone)

    assert len(sent) == 1
    assert phone in sent[0]
