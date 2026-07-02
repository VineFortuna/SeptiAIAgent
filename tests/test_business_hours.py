from datetime import datetime
from zoneinfo import ZoneInfo

import bot as bot_module
from bot import is_within_business_hours

EASTERN = ZoneInfo("America/New_York")


def test_within_business_hours_at_noon() -> None:
    assert is_within_business_hours(datetime(2026, 6, 25, 12, 0, tzinfo=EASTERN))


def test_before_business_hours_at_6am() -> None:
    assert not is_within_business_hours(datetime(2026, 6, 25, 6, 0, tzinfo=EASTERN))


def test_after_business_hours_at_10pm() -> None:
    assert not is_within_business_hours(datetime(2026, 6, 25, 22, 0, tzinfo=EASTERN))


def test_exactly_at_opening_counts_as_open() -> None:
    assert is_within_business_hours(datetime(2026, 6, 25, 7, 0, tzinfo=EASTERN))


def test_exactly_at_closing_counts_as_closed() -> None:
    assert not is_within_business_hours(datetime(2026, 6, 25, 21, 0, tzinfo=EASTERN))


def test_disable_business_hours_env_bypasses_closed_hours(monkeypatch) -> None:
    monkeypatch.setenv("DISABLE_BUSINESS_HOURS", "true")
    assert is_within_business_hours(datetime(2026, 6, 25, 22, 0, tzinfo=EASTERN))


def test_disable_business_hours_env_false_keeps_real_schedule(monkeypatch) -> None:
    monkeypatch.setenv("DISABLE_BUSINESS_HOURS", "false")
    assert not is_within_business_hours(datetime(2026, 6, 25, 22, 0, tzinfo=EASTERN))


def test_queue_message_stores_for_later(bot) -> None:
    bot.queue_message("Hi there", "+40712345678")
    assert "+40712345678" in bot.pending
    assert bot.pending["+40712345678"][0]["message"] == "Hi there"


def test_process_pending_messages_noop_outside_hours(bot, monkeypatch) -> None:
    monkeypatch.setattr(bot_module, "is_within_business_hours", lambda: False)
    bot.queue_message("Hi there", "+40712345678")

    sent = []
    bot.customer_notifier = lambda to, body: (sent.append((to, body)), True)[1]
    bot.process_pending_messages()

    assert sent == []
    assert "+40712345678" in bot.pending


def test_process_pending_messages_sends_and_clears_during_hours(bot, monkeypatch) -> None:
    monkeypatch.setattr(bot_module, "is_within_business_hours", lambda: True)
    bot.queue_message("Hi there", "+40712345678")

    sent = []
    bot.customer_notifier = lambda to, body: (sent.append((to, body)), True)[1]
    bot.process_pending_messages()

    assert len(sent) == 1
    assert sent[0][0] == "+40712345678"
    assert "+40712345678" not in bot.pending


def test_failed_send_keeps_message_queued_for_retry(bot, monkeypatch) -> None:
    monkeypatch.setattr(bot_module, "is_within_business_hours", lambda: True)
    bot.queue_message("Hi there", "+40712345678")

    bot.customer_notifier = lambda to, body: False
    bot.process_pending_messages()

    assert "+40712345678" in bot.pending
