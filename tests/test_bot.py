from bot import BOOKING_NOT_FOUND, HANDOFF_VARIANTS, INTAKE_TRANSITION, REGISTRATION_FALLBACK


def _all_variants(pool: dict[str, list[str]]) -> list[str]:
    return [variant for variants in pool.values() for variant in variants]


def test_registration_question_transitions_to_intake(bot) -> None:
    phone = "+14165550999"
    bot.reply("Hi", phone)  # greeting, lead in "greeted" stage
    reply = bot.reply("Can I sign up for a class?", phone)  # skips rule answer, goes straight to country
    assert any(reply[0].startswith(variant) for variant in _all_variants(INTAKE_TRANSITION))


def test_known_booking_is_returned(bot) -> None:
    reply = bot.reply("What time is my class?", "+14165550100")
    assert "6:00 p.m." in reply[0]


def test_unknown_booking_is_not_invented(bot) -> None:
    phone = "+14165559999"
    bot.reply("Hi", phone)  # greeting
    reply = bot.reply("When is my next class?", phone)  # booking check + country question
    assert any(reply[0].startswith(variant) for variant in _all_variants(BOOKING_NOT_FOUND))


def test_human_request_hands_off(bot) -> None:
    phone = "+14165559999"
    bot.reply("Hi", phone)  # greeting
    reply = bot.reply("Can I speak to a staff member?", phone)  # handoff (no intake pivot)
    assert any(reply[0].startswith(variant) for variant in _all_variants(HANDOFF_VARIANTS))
