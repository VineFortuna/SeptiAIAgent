from bot import REQUIRED_INTAKE_FIELDS
from conftest import make_mock_client


def _intake_result(**overrides) -> dict:
    base = {
        "reply": "Got it!",
        "lang": "en",
        "wants_human": False,
        "thinking_it_over": False,
        "complete": False,
        "multiple_children": None,
    }
    for field in REQUIRED_INTAKE_FIELDS:
        base.setdefault(field, None)
    base.update(overrides)
    return base


def test_new_lead_starts_in_greeted_stage(bot) -> None:
    bot.ai_enabled = True
    bot.client = make_mock_client("faq", {
        "reply": "Hey! How can I help?",
        "lang": "en",
        "wants_human": False,
        "thinking_it_over": False,
    })

    phone = "+40712345678"
    bot.reply("Hi", phone)

    assert bot.leads[phone]["stage"] == "greeted"
    assert bot.leads[phone]["collected_fields"] == []


def test_enrollment_intent_starts_intake(bot) -> None:
    bot.ai_enabled = True
    bot.client = make_mock_client("intake", _intake_result(reply="Sure! What's your name?"))

    phone = "+40712345678"
    bot.reply("I want to sign up", phone)

    assert bot.leads[phone]["stage"] == "intake_in_progress"


def test_intake_completion_persists_all_fields(bot) -> None:
    bot.ai_enabled = True
    result = _intake_result(
        reply="All set, thanks!",
        complete=True,
        parent_name="John",
        child_name="Emma",
        country="Romania",
        child_language_pref="ro",
        timezone="Eastern European Time (EET)",
        child_age=7,
        prior_experience="never played",
        availability_pref="weekday evenings",
        school_dismissal="3:30pm",
        group_pref="exploratori",
        extra_notes=None,
        referral_source="TikTok",
        demo_interest=True,
        multiple_children=False,
    )
    bot.client = make_mock_client("intake", result)

    phone = "+40712345678"
    reply = bot.reply("yes", phone)

    lead = bot.leads[phone]
    assert lead["stage"] == "faq_only"
    assert lead["handed_off"] is True
    assert lead["parent_name"] == "John"
    assert lead["child_language_pref"] == "ro"
    assert lead["collected_fields"] == list(REQUIRED_INTAKE_FIELDS)
    assert reply == ["All set, thanks!"]


def test_declined_demo_is_not_handed_off(bot) -> None:
    bot.ai_enabled = True
    result = _intake_result(reply="No worries, the door's always open!", complete=True, demo_interest=False)
    bot.client = make_mock_client("intake", result)

    phone = "+40712345678"
    bot.reply("no thanks", phone)

    assert bot.leads[phone]["handed_off"] is False


def test_completed_lead_is_not_renotified_on_followup(bot) -> None:
    """Regression test: the orchestrator can mis-route a follow-up back into
    'intake' after it already completed — completion side effects (staff
    notification) must only ever fire once per lead."""
    bot.ai_enabled = True
    notified: list[str] = []
    bot.notifier = lambda msg: notified.append(msg) or True
    result = _intake_result(reply="All set!", complete=True, demo_interest=True)
    bot.client = make_mock_client("intake", result)

    phone = "+40712345678"
    bot.reply("yes", phone)
    bot.reply("thanks!", phone)

    assert len(notified) == 1


def test_multi_child_flag_is_recorded(bot) -> None:
    bot.ai_enabled = True
    result = _intake_result(reply="Got both kids noted!", complete=True, multiple_children=True, demo_interest=True)
    bot.client = make_mock_client("intake", result)

    phone = "+40712345678"
    bot.reply("yes for both", phone)

    assert bot.leads[phone]["multi_child"] is True
