from notifications import send_staff_notification


class _FakeMessages:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def create(self, **kwargs):
        self.sent.append(kwargs)

        class _Result:
            sid = "fake-sid"

        return _Result()


class _FakeTwilioClient:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


def test_notification_sends_with_injected_client(monkeypatch) -> None:
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "fake-sid")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "fake-token")
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    monkeypatch.setenv("STAFF_NOTIFICATION_PHONE", "whatsapp:+40700000000")

    fake_client = _FakeTwilioClient()
    result = send_staff_notification("test body", client=fake_client)

    assert result is True
    assert fake_client.messages.sent[0]["body"] == "test body"


def test_notification_noop_when_unconfigured(monkeypatch) -> None:
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TWILIO_WHATSAPP_FROM", raising=False)
    monkeypatch.delenv("STAFF_NOTIFICATION_PHONE", raising=False)

    fake_client = _FakeTwilioClient()
    result = send_staff_notification("test body", client=fake_client)

    assert result is False
    assert fake_client.messages.sent == []


def test_intake_completion_triggers_injected_notifier(bot) -> None:
    sent: list[str] = []
    bot.notifier = sent.append

    phone = "+40712345678"
    bot.reply("Hi", phone)
    bot.reply("I'm interested in chess classes", phone)  # triggers enrollment intent
    bot.reply("Romanian", phone)
    bot.reply("GMT+2", phone)
    bot.reply("7 years old", phone)
    bot.reply("No, never played", phone)
    bot.reply("Weekday evenings", phone)
    bot.reply("After 3:30pm", phone)
    bot.reply("Exploratori", phone)
    bot.reply("No extra notes", phone)

    assert len(sent) == 1
    assert phone in sent[0]
