import json
from unittest.mock import MagicMock

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


def make_mock_client(route_flow: str, flow_result: dict) -> MagicMock:
    """Fake OpenAI client: every orchestrator call routes to `route_flow`,
    every flow call returns `flow_result` as its structured JSON output."""

    def _create(*, model, instructions, input, text=None, **_kwargs):
        response = MagicMock()
        schema_name = (text or {}).get("format", {}).get("name")
        if schema_name == "route_response":
            response.output_text = json.dumps({"flow": route_flow})
        else:
            response.output_text = json.dumps(flow_result)
        return response

    client = MagicMock()
    client.responses.create.side_effect = _create
    return client
