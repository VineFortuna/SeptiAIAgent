from bot import BOOKING_NOT_FOUND, HANDOFF_VARIANTS, REGISTRATION_FALLBACK


def _all_variants(pool: dict[str, list[str]]) -> list[str]:
    return [variant for variants in pool.values() for variant in variants]


def test_registration_question_returns_helpful_answer(bot) -> None:
    reply = bot.reply("Can I sign up for a class?", "+14165550999")
    assert any(reply.startswith(variant) for variant in _all_variants(REGISTRATION_FALLBACK))


def test_known_booking_is_returned(bot) -> None:
    reply = bot.reply("What time is my class?", "+14165550100")
    assert "6:00 p.m." in reply


def test_unknown_booking_is_not_invented(bot) -> None:
    reply = bot.reply("When is my next class?", "+14165559999")
    assert any(reply.startswith(variant) for variant in _all_variants(BOOKING_NOT_FOUND))


def test_human_request_hands_off(bot) -> None:
    reply = bot.reply("Can I speak to a staff member?", "+14165559999")
    assert any(reply.startswith(variant) for variant in _all_variants(HANDOFF_VARIANTS))
