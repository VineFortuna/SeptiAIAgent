from __future__ import annotations

FLOW_HISTORY_LIMITS: dict[str, int] = {
    "intake": 20,
    "faq": 5,
}


class ConversationStore:
    """Per-phone, per-flow message history.

    Each flow only ever sees its own messages — the faq flow has no visibility
    into what was said during intake, and vice versa. In-memory for now; the
    get/append shape is the seam a future database.py extension plugs into
    (keying conversation_history rows by (phone, flow) instead of just phone).
    """

    def __init__(self) -> None:
        self._histories: dict[tuple[str, str], list[dict[str, str]]] = {}

    def get(self, phone: str, flow: str) -> list[dict[str, str]]:
        return self._histories.get((phone, flow), [])

    def append(self, phone: str, flow: str, role: str, content: str) -> None:
        key = (phone, flow)
        history = self._histories.setdefault(key, [])
        history.append({"role": role, "content": content})
        limit = FLOW_HISTORY_LIMITS.get(flow, 10)
        if len(history) > limit:
            self._histories[key] = history[-limit:]

    def clear(self, phone: str) -> None:
        for key in [k for k in self._histories if k[0] == phone]:
            del self._histories[key]

    def clear_all(self) -> None:
        self._histories.clear()
