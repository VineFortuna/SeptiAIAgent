from bot import HANDOFF_VARIANTS, INTAKE_QUESTIONS


def _all_variants(pool: dict[str, list[str]]) -> list[str]:
    return [variant for variants in pool.values() for variant in variants]


def test_registration_question_transitions_to_intake(bot) -> None:
    phone = "+14165550999"
    bot.reply("Hi", phone)  # greeting, lead in "greeted" stage
    reply = bot.reply("Can I sign up for a class?", phone)
    # enrollment intent → lead is in intake, country question appears somewhere in the reply
    assert bot.leads[phone]["stage"] == "intake_in_progress"
    assert any(
        INTAKE_QUESTIONS["parent_name"]["en"].lower() in r.lower() or INTAKE_QUESTIONS["parent_name"]["ro"].lower() in r.lower()
        for r in reply
    )


def test_human_request_hands_off(bot) -> None:
    phone = "+14165559999"
    bot.reply("Hi", phone)  # greeting
    reply = bot.reply("Can I speak to a staff member?", phone)  # handoff (no intake pivot)
    assert any(reply[0].startswith(variant) for variant in _all_variants(HANDOFF_VARIANTS))
