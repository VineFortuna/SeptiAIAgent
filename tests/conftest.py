import pytest

from bot import ClassAssistant


@pytest.fixture
def bot(tmp_path):
    b = ClassAssistant(
        leads_path=tmp_path / "leads.json",
        notifier=lambda _: None,
    )
    b.ai_enabled = False
    return b
