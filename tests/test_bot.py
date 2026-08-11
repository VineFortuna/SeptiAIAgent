from unittest.mock import MagicMock

from bot import UNAVAILABLE_MESSAGE
from conftest import make_mock_client


def test_ai_disabled_returns_unavailable_message(bot) -> None:
    reply = bot.reply("Hi", "+14165550999")
    assert reply == [UNAVAILABLE_MESSAGE]


def test_orchestrator_failure_returns_unavailable_message(bot) -> None:
    bot.ai_enabled = True
    broken_client = MagicMock()
    broken_client.responses.create.side_effect = RuntimeError("boom")
    bot.client = broken_client

    reply = bot.reply("Hi", "+14165550999")

    assert reply == [UNAVAILABLE_MESSAGE]


def test_flow_failure_after_routing_returns_unavailable_message(bot) -> None:
    bot.ai_enabled = True

    def _create(*, model, instructions, input, text=None, **_kwargs):
        schema_name = (text or {}).get("format", {}).get("name")
        if schema_name == "route_response":
            response = MagicMock()
            response.output_text = '{"flow": "faq"}'
            return response
        raise RuntimeError("flow call boom")

    client = MagicMock()
    client.responses.create.side_effect = _create
    bot.client = client

    reply = bot.reply("Where are you located?", "+14165550999")

    assert reply == [UNAVAILABLE_MESSAGE]


def test_faq_flow_routes_and_returns_its_reply(bot) -> None:
    bot.ai_enabled = True
    bot.client = make_mock_client("faq", {
        "reply": "We're online only, all lessons run on Zoom",
        "lang": "en",
        "wants_human": False,
        "thinking_it_over": False,
    })

    phone = "+14165550999"
    reply = bot.reply("Where are you located?", phone)

    assert reply == ["We're online only, all lessons run on Zoom"]
    assert bot.leads[phone]["stage"] == "greeted"


def test_intake_flow_starts_and_updates_stage(bot) -> None:
    bot.ai_enabled = True
    bot.client = make_mock_client("intake", {
        "reply": "Great! What's your name?",
        "lang": "en",
        "wants_human": False,
        "thinking_it_over": False,
        "complete": False,
        "parent_name": None, "child_name": None, "country": None,
        "child_language_pref": None, "timezone": None, "child_age": None,
        "prior_experience": None, "availability_pref": None, "school_dismissal": None,
        "group_pref": None, "extra_notes": None, "referral_source": None,
        "demo_interest": None, "multiple_children": None,
    })

    phone = "+14165550999"
    reply = bot.reply("I'd like to sign up my son", phone)

    assert reply == ["Great! What's your name?"]
    assert bot.leads[phone]["stage"] == "intake_in_progress"


def test_wants_human_notifies_staff_once_per_conversation(bot) -> None:
    bot.ai_enabled = True
    notified: list[str] = []
    bot.notifier = lambda msg: notified.append(msg) or True
    bot.client = make_mock_client("faq", {
        "reply": "Septi is the right person for that.",
        "lang": "en",
        "wants_human": True,
        "thinking_it_over": False,
    })

    phone = "+14165550999"
    bot.reply("I want to speak to a human", phone)
    bot.reply("still want a human", phone)

    assert len(notified) == 1


def test_thinking_it_over_flag_is_recorded_and_cleared(bot) -> None:
    bot.ai_enabled = True
    phone = "+14165550999"

    bot.client = make_mock_client("faq", {
        "reply": "Take your time!",
        "lang": "en",
        "wants_human": False,
        "thinking_it_over": True,
    })
    bot.reply("let me think about it", phone)
    assert bot.leads[phone]["thinking_it_over"] is True

    bot.client = make_mock_client("faq", {
        "reply": "Sure, ask away!",
        "lang": "en",
        "wants_human": False,
        "thinking_it_over": False,
    })
    bot.reply("actually, what languages do you teach in", phone)
    assert bot.leads[phone]["thinking_it_over"] is False
