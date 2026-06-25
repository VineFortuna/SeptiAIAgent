from bot import CLOSING_MESSAGE, HANDOFF_VARIANTS


def _all_variants(pool: dict[str, list[str]]) -> list[str]:
    return [variant for variants in pool.values() for variant in variants]


def test_new_lead_gets_first_intake_question(bot) -> None:
    reply = bot.reply("Hi, interested in chess lessons", "+40712345678")
    assert reply.strip().endswith("?")


def test_intake_field_is_persisted(bot) -> None:
    phone = "+40712345678"
    bot.reply("Hi", phone)  # creates the lead, asks question 1
    bot.reply("Romanian", phone)  # answers question 1

    lead = bot.leads[phone]
    assert lead["child_language_pref"] == "ro"
    assert "child_language_pref" in lead["collected_fields"]


def test_intake_completes_and_marks_handed_off(bot) -> None:
    phone = "+40712345678"
    bot.reply("Hi", phone)
    bot.reply("Romanian", phone)
    bot.reply("GMT+2", phone)
    bot.reply("7 years old", phone)
    bot.reply("No, never played", phone)
    bot.reply("Weekday evenings", phone)
    final_reply = bot.reply("Exploratori", phone)

    lead = bot.leads[phone]
    assert lead["stage"] == "faq_only"
    assert lead["handed_off"] is True
    assert final_reply in _all_variants(CLOSING_MESSAGE)


def test_known_booking_skips_intake(bot) -> None:
    phone = "+14165550100"
    bot.reply("What time is my class?", phone)
    assert phone not in bot.leads


def test_faq_question_mid_intake_does_not_consume_pending_field(bot) -> None:
    phone = "+40712345678"
    bot.reply("Hi", phone)  # pending field: child_language_pref
    reply = bot.reply("Can I speak to a staff member?", phone)

    lead = bot.leads[phone]
    assert reply in _all_variants(HANDOFF_VARIANTS)
    assert lead["collected_fields"] == []


def test_empty_message_during_intake_does_not_crash_or_lose_progress(bot) -> None:
    phone = "+40712345678"
    bot.reply("Hi", phone)  # pending field: child_language_pref
    reply = bot.reply("   ", phone)

    lead = bot.leads[phone]
    assert reply  # some non-empty reply, no crash
    assert lead["collected_fields"] == []


def test_gibberish_answer_is_stored_verbatim_and_advances_intake(bot) -> None:
    phone = "+40712345678"
    bot.reply("Hi", phone)  # pending field: child_language_pref
    bot.reply("asdkjfh qwerty zzz", phone)

    lead = bot.leads[phone]
    assert lead["child_language_pref"] == "asdkjfh qwerty zzz"
    assert "child_language_pref" in lead["collected_fields"]


def test_lead_resumes_intake_after_gap_without_restarting(bot) -> None:
    phone = "+40712345678"
    bot.reply("Hi", phone)
    bot.reply("Romanian", phone)
    bot.reply("GMT+2", phone)

    fields_before = list(bot.leads[phone]["collected_fields"])

    # Simulate a long gap (e.g. the lead goes quiet for days) - nothing in the
    # code depends on elapsed time, so the next message should just continue
    # from the same pending field, not restart the intake.
    reply = bot.reply("7 years old", phone)

    assert reply.strip().endswith("?")
    assert bot.leads[phone]["collected_fields"] == [*fields_before, "child_age"]


def test_handed_off_lead_does_not_restart_intake_later(bot) -> None:
    phone = "+40712345678"
    bot.reply("Hi", phone)
    bot.reply("Romanian", phone)
    bot.reply("GMT+2", phone)
    bot.reply("7 years old", phone)
    bot.reply("No, never played", phone)
    bot.reply("Weekday evenings", phone)
    bot.reply("Exploratori", phone)

    # Lead is now handed off. A message much later should be treated as a
    # normal FAQ question, not restart the intake questionnaire.
    reply = bot.reply("Can I speak to a staff member?", phone)

    assert reply in _all_variants(HANDOFF_VARIANTS)
    assert bot.leads[phone]["stage"] == "faq_only"
