import pytest

from bot import ClassAssistant


@pytest.fixture
def bot(tmp_path):
    return ClassAssistant(
        leads_path=tmp_path / "leads.json",
        pending_path=tmp_path / "pending_messages.json",
        history_path=tmp_path / "conversation_history.json",
        notifier=lambda _: None,
        customer_notifier=lambda _to, _body: True,
    )
