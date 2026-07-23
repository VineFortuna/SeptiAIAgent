from bot import infer_currency_bucket


def test_uk_number_maps_to_gbp() -> None:
    bucket, code = infer_currency_bucket("+447911123456")
    assert bucket == "GBP"
    assert code == "44"


def test_romania_number_maps_to_ron() -> None:
    bucket, code = infer_currency_bucket("+40712345678")
    assert bucket == "RON"
    assert code == "40"


def test_canadian_number_maps_to_cad() -> None:
    bucket, code = infer_currency_bucket("+14165550100")  # 416 = Toronto
    assert bucket == "CAD"
    assert code == "1"


def test_us_number_maps_to_usd() -> None:
    bucket, code = infer_currency_bucket("+12125550100")  # 212 = New York
    assert bucket == "USD"
    assert code == "1"


def test_unrecognized_country_defaults_to_eur() -> None:
    bucket, code = infer_currency_bucket("+999999999")
    assert bucket == "EUR"
    assert code is None


def test_pricing_question_mentions_currency_for_uk_number(bot) -> None:
    if not bot.ai_enabled:
        return

    phone = "+447911123456"
    bot.reply("Hi", phone)
    bot.reply("I want to sign up", phone)  # enrollment signal → starts intake, asks country
    bot.reply("UK", phone)                 # stores country, sets currency_bucket=GBP
    reply = bot.reply("How much does the standard package cost?", phone)
    assert "£" in reply[0] or "GBP" in reply[0]
