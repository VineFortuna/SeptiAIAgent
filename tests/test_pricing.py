from bot import infer_currency_bucket


def test_uk_number_maps_to_gbp() -> None:
    bucket, code = infer_currency_bucket("+447911123456")
    assert bucket == "GBP"
    assert code == "44"


def test_romania_number_maps_to_ron() -> None:
    bucket, code = infer_currency_bucket("+40712345678")
    assert bucket == "RON"
    assert code == "40"


def test_us_canada_number_maps_to_usd_can() -> None:
    bucket, code = infer_currency_bucket("+14165550100")
    assert bucket == "USD_CAN"
    assert code == "1"


def test_unrecognized_country_defaults_to_eur() -> None:
    bucket, code = infer_currency_bucket("+999999999")
    assert bucket == "EUR"
    assert code is None


def test_pricing_question_mentions_currency_for_uk_number(bot) -> None:
    if not bot.ai_enabled:
        return

    phone = "+447911123456"
    bot.reply("Hi", phone)  # first message always starts intake
    reply = bot.reply("How much does the standard package cost?", phone)
    assert "£" in reply or "GBP" in reply
