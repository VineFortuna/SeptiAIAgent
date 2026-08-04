from bot import CLOSING_MESSAGE, HANDOFF_VARIANTS, INTAKE_QUESTIONS


def _all_variants(pool: dict[str, list[str]]) -> list[str]:
    return [variant for variants in pool.values() for variant in variants]


def test_new_lead_gets_greeting_then_country_question(bot) -> None:
    phone = "+40712345678"
    # Pure greeting → bot says hi, no intake question yet
    first_reply = bot.reply("Hi", phone)
    assert first_reply[-1].strip().endswith("?")
    assert "country" not in first_reply[-1].lower() and "tara" not in first_reply[-1].lower()
    # Clear enrollment signal → bot starts intake and asks country
    second_reply = bot.reply("I'd like to sign up", phone)
    assert second_reply[-1].strip().endswith("?")


def test_pure_greeting_creates_greeted_lead(bot) -> None:
    phone = "+40712345678"
    bot.reply("Hi", phone)
    # Lead created in "greeted" stage — intake has not started yet
    assert bot.leads[phone]["stage"] == "greeted"
    assert bot.leads[phone]["collected_fields"] == []


def test_intake_starts_on_second_message(bot) -> None:
    phone = "+40712345678"
    bot.reply("Hi", phone)                       # greeting → "greeted" stage
    bot.reply("I want to sign up", phone)      # second msg → "intake_in_progress"
    assert bot.leads[phone]["stage"] == "intake_in_progress"


def test_intake_field_is_persisted(bot) -> None:
    phone = "+40712345678"
    bot.reply("Hi", phone)
    bot.reply("I want to sign up", phone)  # greeted → starts intake
    bot.reply("Romania", phone)             # stores country, asks child_language_pref
    bot.reply("Romanian", phone)            # stores child_language_pref = "ro"

    lead = bot.leads[phone]
    assert lead["child_language_pref"] == "ro"
    assert "child_language_pref" in lead["collected_fields"]


def test_intake_completes_and_marks_handed_off(bot) -> None:
    phone = "+40712345678"
    bot.reply("Hi", phone)
    bot.reply("I want to sign up", phone)  # greeted → starts intake
    bot.reply("Romanian", phone)             # country + child_language_pref (multi-field)
    bot.reply("GMT+2", phone)
    bot.reply("7 years old", phone)
    bot.reply("No, never played", phone)
    bot.reply("Weekday evenings", phone)
    bot.reply("After 3:30pm", phone)
    bot.reply("Exploratori", phone)
    bot.reply("Nothing else, thanks!", phone)
    bot.reply("TikTok", phone)               # referral_source → asks demo_interest
    final_reply = bot.reply("yes", phone)    # demo_interest → closes intake

    lead = bot.leads[phone]
    assert lead["stage"] == "faq_only"
    assert lead["handed_off"] is True
    assert final_reply[0] in _all_variants(CLOSING_MESSAGE)


def test_greeting_mid_intake_repeats_pending_question(bot) -> None:
    phone = "+40712345678"
    bot.reply("Hi", phone)
    bot.reply("I want to sign up", phone)  # greeted → starts intake
    # Saying hello mid-intake should warmly re-ask the parent_name question in one message
    reply = bot.reply("Hello", phone)
    assert any(INTAKE_QUESTIONS["parent_name"]["en"] in r or INTAKE_QUESTIONS["parent_name"]["ro"] in r for r in reply)


def test_faq_question_mid_intake_does_not_consume_pending_field(bot) -> None:
    phone = "+40712345678"
    bot.reply("Hi", phone)
    bot.reply("I want to sign up", phone)  # greeted → starts intake
    bot.reply("Anna", phone)               # parent_name stored, pending: child_name
    reply = bot.reply("Can I speak to a staff member?", phone)

    lead = bot.leads[phone]
    # FAQ answer is returned; pending field (child_name) is NOT consumed by the off-topic message
    assert reply[0] in _all_variants(HANDOFF_VARIANTS)
    assert "child_name" not in lead["collected_fields"]


def test_empty_message_during_intake_does_not_crash_or_lose_progress(bot) -> None:
    phone = "+40712345678"
    bot.reply("Hi", phone)
    bot.reply("I want to sign up", phone)  # greeted → starts intake
    reply = bot.reply("   ", phone)

    lead = bot.leads[phone]
    assert reply  # some non-empty reply, no crash
    assert lead["collected_fields"] == []


def test_gibberish_answer_is_stored_verbatim_and_advances_intake(bot) -> None:
    phone = "+40712345678"
    bot.reply("Hi", phone)
    bot.reply("I want to sign up", phone)  # greeted → starts intake
    bot.reply("asdkjfh qwerty zzz", phone)   # stored as parent_name verbatim (title-cased)

    lead = bot.leads[phone]
    assert lead["parent_name"] == "Asdkjfh Qwerty Zzz"
    assert "parent_name" in lead["collected_fields"]


def test_lead_resumes_intake_after_gap_without_restarting(bot) -> None:
    phone = "+40712345678"
    bot.reply("Hi", phone)
    bot.reply("I want to sign up", phone)  # greeted → starts intake
    bot.reply("John", phone)               # parent_name
    bot.reply("Emma", phone)               # child_name
    bot.reply("Romanian", phone)           # country + child_language_pref (multi-field)
    bot.reply("GMT+2", phone)              # timezone

    fields_before = list(bot.leads[phone]["collected_fields"])

    # Simulate a long gap — the next message should continue from the same pending field
    reply = bot.reply("7 years old", phone)

    assert reply[-1].strip().endswith("?")
    assert bot.leads[phone]["collected_fields"] == [*fields_before, "child_age"]


def test_handed_off_lead_does_not_restart_intake_later(bot) -> None:
    phone = "+40712345678"
    bot.reply("Hi", phone)
    bot.reply("I want to sign up", phone)
    bot.reply("Romanian", phone)
    bot.reply("GMT+2", phone)
    bot.reply("7 years old", phone)
    bot.reply("No, never played", phone)
    bot.reply("Weekday evenings", phone)
    bot.reply("After 3:30pm", phone)
    bot.reply("Exploratori", phone)
    bot.reply("No extra notes", phone)
    bot.reply("TikTok", phone)   # referral_source → asks demo_interest
    bot.reply("yes", phone)      # demo_interest → closes intake

    # Lead is now handed off. A later message should be a normal FAQ, not restart intake.
    reply = bot.reply("Can I speak to a staff member?", phone)

    assert reply[0] in _all_variants(HANDOFF_VARIANTS)
    assert bot.leads[phone]["stage"] == "faq_only"
