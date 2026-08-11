from conftest import make_mock_client
from conversation_store import ConversationStore


def test_history_accumulates_within_a_flow() -> None:
    store = ConversationStore()
    store.append("+1416", "faq", "user", "Hi")
    store.append("+1416", "faq", "assistant", "Hello!")

    assert store.get("+1416", "faq") == [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
    ]


def test_history_is_isolated_per_flow() -> None:
    store = ConversationStore()
    store.append("+1416", "faq", "user", "faq question")
    store.append("+1416", "intake", "user", "intake answer")

    assert store.get("+1416", "faq") == [{"role": "user", "content": "faq question"}]
    assert store.get("+1416", "intake") == [{"role": "user", "content": "intake answer"}]


def test_history_is_isolated_per_phone() -> None:
    store = ConversationStore()
    store.append("+1416", "faq", "user", "a")
    store.append("+1647", "faq", "user", "b")

    assert store.get("+1416", "faq") == [{"role": "user", "content": "a"}]
    assert store.get("+1647", "faq") == [{"role": "user", "content": "b"}]


def test_faq_history_capped_at_its_configured_limit() -> None:
    store = ConversationStore()
    for i in range(10):
        store.append("+1416", "faq", "user", str(i))

    history = store.get("+1416", "faq")
    assert len(history) == 5
    assert history[0]["content"] == "5"


def test_intake_history_has_a_higher_cap_than_faq() -> None:
    store = ConversationStore()
    for i in range(25):
        store.append("+1416", "intake", "user", str(i))

    assert len(store.get("+1416", "intake")) == 20


def test_clear_removes_every_flow_for_that_phone() -> None:
    store = ConversationStore()
    store.append("+1416", "faq", "user", "a")
    store.append("+1416", "intake", "user", "b")

    store.clear("+1416")

    assert store.get("+1416", "faq") == []
    assert store.get("+1416", "intake") == []


def test_faq_flow_call_receives_prior_history(bot) -> None:
    bot.ai_enabled = True
    bot.client = make_mock_client("faq", {
        "reply": "Sure, happy to help!",
        "lang": "en",
        "wants_human": False,
        "thinking_it_over": False,
    })

    phone = "+447911123456"
    bot.reply("Hi", phone)
    bot.reply("What classes do you offer?", phone)

    last_call_kwargs = bot.client.responses.create.call_args_list[-1].kwargs
    input_sent = last_call_kwargs["input"]

    assert isinstance(input_sent, list)
    assert input_sent[-1] == {"role": "user", "content": "What classes do you offer?"}
    assert any(m["role"] == "assistant" for m in input_sent[:-1])
