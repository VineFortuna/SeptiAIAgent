from unittest.mock import MagicMock


def test_history_accumulates_across_replies(bot) -> None:
    phone = "+14165559010"
    bot.reply("Hi", phone)
    bot.reply("What classes do you offer?", phone)

    history = bot._conversation_history[phone]
    assert len(history) == 4
    assert history[0] == {"role": "user", "content": "Hi"}
    assert history[2] == {"role": "user", "content": "What classes do you offer?"}


def test_history_is_isolated_per_phone(bot) -> None:
    bot.reply("Hi", "+14165559011")
    bot.reply("Salut", "+14165559012")

    assert "+14165559011" in bot._conversation_history
    assert "+14165559012" in bot._conversation_history
    assert len(bot._conversation_history["+14165559011"]) == 2
    assert len(bot._conversation_history["+14165559012"]) == 2


def test_history_capped_at_20_messages(bot) -> None:
    phone = "+14165559013"
    for _ in range(12):
        bot.reply("Hi", phone)

    assert len(bot._conversation_history[phone]) == 20


def test_ai_reply_receives_prior_history(bot) -> None:
    bot.ai_enabled = True
    mock_response = MagicMock()
    mock_response.output_text = "Standard is £56/month"
    mock_client = MagicMock()
    mock_client.responses.create.return_value = mock_response
    bot.client = mock_client

    phone = "+447911123456"
    bot.reply("Hi", phone)
    bot.reply("interested in chess", phone)  # creates lead, asks country
    bot.reply("UK", phone)                   # stores country, next intake question

    bot.reply("How much does the standard package cost?", phone)

    input_sent = mock_client.responses.create.call_args[1]["input"]

    assert isinstance(input_sent, list)
    assert len(input_sent) >= 3
    assert input_sent[-1]["role"] == "user"
    assert input_sent[-1]["content"] == "How much does the standard package cost?"
    assert any(m["role"] == "assistant" for m in input_sent[:-1])
