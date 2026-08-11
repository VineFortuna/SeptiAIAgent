from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from conversation_store import ConversationStore
from notifications import send_staff_notification, send_whatsapp_message
import database as db

# In production set DATA_DIR to a persistent volume path (e.g. /data on Render).
# Falls back to the project directory for local development.
_data_dir_env = os.getenv("DATA_DIR", "").strip()
BASE_DIR = Path(_data_dir_env) if _data_dir_env else Path(__file__).resolve().parent
FLOWS_DIR = Path(__file__).resolve().parent / "flows"

UNAVAILABLE_MESSAGE = (
    "Sorry, I'm having a technical issue right now, someone from our team will "
    "reach out to you soon. / Ne pare rău, avem o problemă tehnică momentan, "
    "cineva din echipă te va contacta în curând."
)

REQUIRED_INTAKE_FIELDS: tuple[str, ...] = (
    "parent_name",
    "child_name",
    "country",
    "child_language_pref",
    "timezone",
    "child_age",
    "prior_experience",
    "availability_pref",
    "school_dismissal",
    "group_pref",
    "extra_notes",
    "referral_source",
    "demo_interest",
)

# Longest-prefix match against E.164 calling codes -> which pricing bucket to quote.
# Starter list based on where the Sep7Ro diaspora audience is known to live; easy to
# extend as leads arrive from new countries.
# Note: +1 (US vs Canada) is handled separately via area code — see CANADIAN_AREA_CODES.
COUNTRY_CODE_CURRENCY: dict[str, str] = {
    "44": "GBP",    # UK
    "40": "RON",    # Romania
    "373": "RON",   # Moldova
    "49": "EUR",
    "33": "EUR",
    "39": "EUR",
    "34": "EUR",
    "31": "EUR",
    "32": "EUR",
    "43": "EUR",
    "351": "EUR",
    "353": "EUR",
    "30": "EUR",
    "352": "EUR",
}
DEFAULT_CURRENCY_BUCKET = "EUR"

# All assigned Canadian NPA (area) codes. Used to tell a Canadian +1 number from
# a US +1 number — the only reliable way since they share the same country code.
CANADIAN_AREA_CODES: frozenset[str] = frozenset({
    "204", "226", "236", "249", "250", "289",
    "306", "343", "365", "367", "368", "382",
    "403", "416", "418", "428", "431", "437", "438", "450",
    "506", "514", "519", "548", "579", "581", "587",
    "604", "613", "639", "647", "672",
    "705", "709", "742", "778", "780", "782", "807", "819", "825",
    "867", "873", "902", "905",
})


def infer_currency_bucket(phone: str) -> tuple[str, str | None]:
    """Infer which pricing bucket to quote from an E.164 phone number's calling code."""
    digits = re.sub(r"[^0-9]", "", phone)

    # +1 covers both US and Canada; use the 3-digit area code to tell them apart.
    if digits and digits[0] == "1":
        area_code = digits[1:4] if len(digits) >= 4 else ""
        return ("CAD", "1") if area_code in CANADIAN_AREA_CODES else ("USD", "1")

    for length in (3, 2, 1):
        prefix = digits[:length]

        if prefix in COUNTRY_CODE_CURRENCY:
            return COUNTRY_CODE_CURRENCY[prefix], prefix

    return DEFAULT_CURRENCY_BUCKET, None


# --- Structured-output schemas -------------------------------------------------

_FLOW_BASE_PROPERTIES: dict[str, Any] = {
    "reply": {"type": "string", "description": "The WhatsApp message to send back to the parent."},
    "lang": {"type": "string", "enum": ["en", "ro"], "description": "Language you just replied in."},
    "wants_human": {"type": "boolean", "description": "True if the parent explicitly asked for a staff member/Septi/a real person, or raised a complaint, refund, or emergency."},
    "thinking_it_over": {"type": "boolean", "description": "True if the parent said they need time to think it over or aren't ready to decide."},
}
_FLOW_BASE_REQUIRED: list[str] = ["reply", "lang", "wants_human", "thinking_it_over"]

FAQ_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "name": "faq_response",
    "schema": {
        "type": "object",
        "properties": _FLOW_BASE_PROPERTIES,
        "required": _FLOW_BASE_REQUIRED,
        "additionalProperties": False,
    },
    "strict": True,
}

_INTAKE_FIELD_PROPERTIES: dict[str, Any] = {
    "parent_name": {"type": ["string", "null"]},
    "child_name": {"type": ["string", "null"]},
    "country": {"type": ["string", "null"]},
    "child_language_pref": {"type": ["string", "null"], "enum": ["ro", "en", "both", None]},
    "timezone": {"type": ["string", "null"]},
    "child_age": {"type": ["integer", "null"]},
    "prior_experience": {"type": ["string", "null"]},
    "availability_pref": {"type": ["string", "null"]},
    "school_dismissal": {"type": ["string", "null"]},
    "group_pref": {"type": ["string", "null"], "enum": ["exploratori", "strategi", None]},
    "extra_notes": {"type": ["string", "null"]},
    "referral_source": {"type": ["string", "null"]},
    "demo_interest": {"type": ["boolean", "null"]},
    "multiple_children": {"type": ["boolean", "null"], "description": "True if the parent mentioned more than one child to enroll."},
}

INTAKE_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "name": "intake_response",
    "schema": {
        "type": "object",
        "properties": {
            **_FLOW_BASE_PROPERTIES,
            "complete": {"type": "boolean", "description": "True only once every field has a value and reply is a closing message."},
            **_INTAKE_FIELD_PROPERTIES,
        },
        "required": _FLOW_BASE_REQUIRED + ["complete"] + list(_INTAKE_FIELD_PROPERTIES.keys()),
        "additionalProperties": False,
    },
    "strict": True,
}

ROUTE_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "name": "route_response",
    "schema": {
        "type": "object",
        "properties": {"flow": {"type": "string", "enum": ["intake", "faq"]}},
        "required": ["flow"],
        "additionalProperties": False,
    },
    "strict": True,
}


class ClassAssistant:
    def __init__(
        self,
        leads_path: Path | None = None,
        notifier: Callable[[str], bool] | None = None,
    ) -> None:
        self.company_data = self._load_json("company_data.json")

        self.leads_path = leads_path or (BASE_DIR / "leads.json")
        self._db_available = db.init_db()
        print(f"[DB] available={self._db_available}")
        if self._db_available:
            db_leads = db.load_leads()
            if db_leads:
                self.leads = db_leads
            else:
                # First run: migrate existing JSON leads into the database
                self.leads = self._load_leads(self.leads_path)
                if self.leads:
                    db.save_all_leads(self.leads)
        else:
            self.leads = self._load_leads(self.leads_path)

        self.notifier = notifier or send_staff_notification
        self._leads_lock = Lock()
        self.store = ConversationStore()

        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o").strip()
        self.orchestrator_model = os.getenv("OPENAI_ORCHESTRATOR_MODEL", "").strip() or self.model
        self.ai_enabled = bool(self.api_key)
        self.client = None

        if self.ai_enabled:
            from openai import OpenAI

            self.client = OpenAI(api_key=self.api_key)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @staticmethod
    def _load_json(filename: str) -> dict[str, Any]:
        path = BASE_DIR / filename

        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Could not load {filename}: {exc}") from exc

    @staticmethod
    def _load_leads(path: Path) -> dict[str, Any]:
        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_leads(self) -> None:
        # Must be called while _leads_lock is held (directly or via _reply_locked).
        if self._db_available:
            db.save_all_leads(self.leads)
        with self.leads_path.open("w", encoding="utf-8") as file:
            json.dump(self.leads, file, ensure_ascii=False, indent=2)

    def clear_state(self) -> None:
        """Wipe all leads and conversation history from memory and disk."""
        with self._leads_lock:
            self.leads = {}
            self.store.clear_all()
            if self._db_available:
                db.delete_all_leads()
                db.delete_all_history()
            self._save_leads()

    def clear_lead(self, phone: str) -> bool:
        """Remove one phone's lead and conversation history. Returns True if the lead existed."""
        phone = self._normalize_phone(phone)
        with self._leads_lock:
            existed = phone in self.leads
            self.leads.pop(phone, None)
            self.store.clear(phone)
            if self._db_available:
                db.delete_lead(phone)
                db.delete_history(phone)
            self._save_leads()
        return existed

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        return re.sub(r"[^0-9+]", "", phone)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _create_lead(self, phone: str) -> dict[str, Any]:
        now = self._now_iso()
        lead: dict[str, Any] = {
            "stage": "greeted",
            "lang": "en",
            "collected_fields": [],
            "handed_off": False,
            "created_at": now,
            "updated_at": now,
        }
        for field in REQUIRED_INTAKE_FIELDS:
            lead[field] = None
        self.leads[phone] = lead
        return lead

    # ------------------------------------------------------------------
    # Prompt loading
    # ------------------------------------------------------------------

    @staticmethod
    def _read_prompt(filename: str) -> str:
        # Re-read from disk on every call (not cached) so editing a prompt file
        # takes effect on the next message without restarting the process.
        return (FLOWS_DIR / filename).read_text(encoding="utf-8").strip()

    # ------------------------------------------------------------------
    # Pricing data scoping (guardrail: only the customer's own currency is
    # ever included in what the faq flow sees, so it can't leak other
    # regions' rates)
    # ------------------------------------------------------------------

    def _scoped_company_data(self, phone: str) -> tuple[dict[str, Any], str, bool]:
        bucket, country_code = infer_currency_bucket(phone)
        data = dict(self.company_data)
        pricing = data.get("pricing")

        if isinstance(pricing, dict) and isinstance(pricing.get("rates"), dict):
            data["pricing"] = {
                **pricing,
                "rates": {bucket: pricing["rates"].get(bucket, {})},
            }

        return data, bucket, bool(country_code)

    @staticmethod
    def _currency_note(bucket: str, has_country_code: bool) -> str:
        if has_country_code:
            return (
                f"This customer's currency is {bucket}. Only {bucket} pricing is "
                f"included below, on purpose, other currencies have been removed. "
                f"If asked about pricing in another currency, say you only quote in "
                f"{bucket} for them and never guess a conversion."
            )
        return (
            f"This customer's country couldn't be determined from their phone "
            f"number, so only {bucket} pricing is included below, on purpose. "
            f"Default to it and mention you're defaulting to it."
        )

    # ------------------------------------------------------------------
    # Orchestrator + flows
    # ------------------------------------------------------------------

    @staticmethod
    def _home_flow(lead: dict[str, Any]) -> str:
        return "intake" if lead.get("stage") == "intake_in_progress" else "faq"

    def _last_assistant_message(self, phone: str, flow: str) -> str:
        history = self.store.get(phone, flow)
        for entry in reversed(history):
            if entry["role"] == "assistant":
                return entry["content"]
        return ""

    def _choose_flow(
        self, active_flow: str, last_assistant_message: str, user_message: str, intake_already_completed: bool
    ) -> str:
        instructions = self._read_prompt("orchestrator_prompt.txt")
        context = (
            f"Current active flow: {active_flow}\n"
            f"Has this parent already completed intake for a child: {intake_already_completed}\n"
            f"Last message from the assistant in that flow: {last_assistant_message!r}\n"
            f"User's latest message: {user_message!r}"
        )

        response = self.client.responses.create(
            model=self.orchestrator_model,
            instructions=instructions,
            input=[{"role": "user", "content": context}],
            text={"format": ROUTE_RESPONSE_FORMAT},
        )
        result = json.loads(response.output_text)
        flow = result.get("flow")
        return flow if flow in ("intake", "faq") else active_flow

    def _run_faq_flow(self, phone: str, message: str) -> dict[str, Any]:
        template = self._read_prompt("faq_prompt.txt")
        scoped_data, bucket, has_country = self._scoped_company_data(phone)
        currency_note = self._currency_note(bucket, has_country)
        approved_information = f"{currency_note}\n\n{json.dumps(scoped_data, ensure_ascii=False, indent=2)}"
        instructions = template.format(approved_information=approved_information)

        history = self.store.get(phone, "faq")
        input_messages = [*history, {"role": "user", "content": message}]

        response = self.client.responses.create(
            model=self.model,
            instructions=instructions,
            input=input_messages,
            text={"format": FAQ_RESPONSE_FORMAT},
        )
        return json.loads(response.output_text)

    def _run_intake_flow(self, phone: str, message: str) -> dict[str, Any]:
        instructions = self._read_prompt("intake_prompt.txt")
        history = self.store.get(phone, "intake")
        input_messages = [*history, {"role": "user", "content": message}]

        response = self.client.responses.create(
            model=self.model,
            instructions=instructions,
            input=input_messages,
            text={"format": INTAKE_RESPONSE_FORMAT},
        )
        return json.loads(response.output_text)

    def _complete_intake(self, phone: str, lead: dict[str, Any], result: dict[str, Any]) -> None:
        for field in REQUIRED_INTAKE_FIELDS:
            lead[field] = result.get(field)
        lead["multi_child"] = bool(result.get("multiple_children", False))
        lead["collected_fields"] = list(REQUIRED_INTAKE_FIELDS)
        lead["stage"] = "faq_only"
        demo_yes = bool(lead.get("demo_interest"))
        lead["handed_off"] = demo_yes
        if demo_yes:
            self._notify_staff_lead_ready(phone, lead)

    def _notify_staff_lead_ready(self, phone: str, lead: dict[str, Any]) -> None:
        wa_link = f"https://wa.me/{phone.lstrip('+')}"
        multi_note = " (multiple children mentioned — confirm details)" if lead.get("multi_child") else ""

        lines = [
            "New lead ready for follow-up 👋",
            f"WhatsApp: {phone} | {wa_link}",
            f"Parent: {lead.get('parent_name') or '-'}",
            f"Child: {lead.get('child_name') or '-'}",
            "",
            f"Country: {lead.get('country') or '-'}",
            f"Class language: {lead.get('child_language_pref') or '-'}",
            f"Time zone: {lead.get('timezone') or '-'}",
            f"Child's age: {lead.get('child_age') or '-'}{multi_note}",
            f"Chess experience: {lead.get('prior_experience') or '-'}",
            f"Availability: {lead.get('availability_pref') or '-'}",
            f"Free from: {lead.get('school_dismissal') or '-'}",
            f"Group preference: {lead.get('group_pref') or '-'}",
            f"Extra notes: {lead.get('extra_notes') or '-'}",
            f"Heard about us via: {lead.get('referral_source') or '-'}",
        ]

        self.notifier("\n".join(lines))

    def _notify_staff_human_request(self, phone: str) -> None:
        wa_link = f"https://wa.me/{phone.lstrip('+')}"
        self.notifier(f"Parent asked to speak with a human 👋\nWhatsApp: {phone} | {wa_link}")

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def reply(self, message: str, sender_phone: str) -> list[str]:
        with self._leads_lock:
            return self._reply_locked(message, sender_phone)

    def _reply_locked(self, message: str, sender_phone: str) -> list[str]:
        if not self.ai_enabled:
            return [UNAVAILABLE_MESSAGE]

        phone = self._normalize_phone(sender_phone)
        lead = self.leads.get(phone)
        if lead is None:
            lead = self._create_lead(phone)

        lead["updated_at"] = self._now_iso()

        home_flow = self._home_flow(lead)
        last_assistant_message = self._last_assistant_message(phone, home_flow)

        try:
            chosen_flow = self._choose_flow(
                home_flow, last_assistant_message, message, lead.get("stage") == "faq_only"
            )
        except Exception as exc:
            print(f"[AI ERROR - orchestrator] {type(exc).__name__}: {exc}")
            self._save_leads()
            return [UNAVAILABLE_MESSAGE]

        print(f"[DEBUG] home_flow={home_flow} chosen_flow={chosen_flow}")

        if chosen_flow == "intake" and lead.get("stage") not in ("intake_in_progress", "faq_only"):
            lead["stage"] = "intake_in_progress"

        try:
            if chosen_flow == "intake":
                result = self._run_intake_flow(phone, message)
            else:
                result = self._run_faq_flow(phone, message)
        except Exception as exc:
            print(f"[AI ERROR - {chosen_flow}] {type(exc).__name__}: {exc}")
            self._save_leads()
            return [UNAVAILABLE_MESSAGE]

        print(
            f"[DEBUG] complete={result.get('complete', False)} "
            f"wants_human={result.get('wants_human')} thinking_it_over={result.get('thinking_it_over')}"
        )

        reply_text = result.get("reply", "").strip() or UNAVAILABLE_MESSAGE
        lead["lang"] = result.get("lang") or lead.get("lang", "en")

        if result.get("wants_human") and not lead.get("human_requested"):
            lead["human_requested"] = True
            self._notify_staff_human_request(phone)

        if result.get("thinking_it_over"):
            lead["thinking_it_over"] = True
            lead["thinking_it_over_at"] = self._now_iso()
            lead["thinking_it_over_nudge_sent"] = False
        elif lead.get("thinking_it_over"):
            lead["thinking_it_over"] = False

        if chosen_flow == "intake" and result.get("complete") and lead.get("stage") != "faq_only":
            self._complete_intake(phone, lead, result)

        self.store.append(phone, chosen_flow, "user", message)
        self.store.append(phone, chosen_flow, "assistant", reply_text)
        self._save_leads()

        return [reply_text]

    # ------------------------------------------------------------------
    # Proactive nudges (outbound, no live message to react to)
    # ------------------------------------------------------------------

    def _generate_nudge_message(self, reason: str, lang: str) -> str | None:
        if not self.ai_enabled:
            return None
        try:
            template = self._read_prompt("nudge_prompt.txt")
            instructions = template.format(reason=reason, lang="Romanian" if lang == "ro" else "English")
            response = self.client.responses.create(
                model=self.model,
                instructions=instructions,
                input=[{"role": "user", "content": "Write the check-in message now."}],
            )
            return response.output_text.strip()
        except Exception as exc:
            print(f"[AI ERROR - nudge] {type(exc).__name__}: {exc}")
            return None

    def send_abandoned_intake_nudges(self) -> None:
        """Send a one-time gentle follow-up to parents who went silent mid-intake for 24+ hours."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        with self._leads_lock:
            leads_snapshot = list(self.leads.items())

        for phone, lead in leads_snapshot:
            if lead.get("stage") != "intake_in_progress":
                continue
            if lead.get("nudge_sent"):
                continue

            last_seen_str = lead.get("updated_at") or lead.get("created_at")
            if not last_seen_str:
                continue

            try:
                last_seen = datetime.fromisoformat(last_seen_str)
            except Exception:
                continue

            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)

            if last_seen >= cutoff:
                continue

            lang = lead.get("lang", "en")
            message = self._generate_nudge_message("abandoned mid-intake, 24+ hours silent", lang)
            if not message:
                continue

            if send_whatsapp_message(f"whatsapp:{phone}", message):
                with self._leads_lock:
                    lead["nudge_sent"] = True
                    self._save_leads()

    def send_post_intake_nudges(self) -> None:
        """Send a one-time check-in to parents who completed intake but haven't heard back in 48+ hours."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

        with self._leads_lock:
            leads_snapshot = list(self.leads.items())

        for phone, lead in leads_snapshot:
            if lead.get("stage") != "faq_only":
                continue
            if lead.get("post_intake_nudge_sent"):
                continue
            if lead.get("demo_completed"):
                continue

            last_seen_str = lead.get("updated_at") or lead.get("created_at")
            if not last_seen_str:
                continue

            try:
                last_seen = datetime.fromisoformat(last_seen_str)
            except Exception:
                continue

            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)

            if last_seen >= cutoff:
                continue

            lang = lead.get("lang", "en")
            message = self._generate_nudge_message("completed intake 48+ hours ago, demo not yet scheduled", lang)
            if not message:
                continue

            if send_whatsapp_message(f"whatsapp:{phone}", message):
                with self._leads_lock:
                    lead["post_intake_nudge_sent"] = True
                    self._save_leads()

    def send_thinking_it_over_nudges(self) -> None:
        """Send a one-time warm follow-up to parents who said 'let me think about it' 48+ hours ago."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

        with self._leads_lock:
            leads_snapshot = list(self.leads.items())

        for phone, lead in leads_snapshot:
            if not lead.get("thinking_it_over"):
                continue
            if lead.get("thinking_it_over_nudge_sent"):
                continue

            thinking_since_str = lead.get("thinking_it_over_at")
            if not thinking_since_str:
                continue

            try:
                thinking_since = datetime.fromisoformat(thinking_since_str)
            except Exception:
                continue

            if thinking_since.tzinfo is None:
                thinking_since = thinking_since.replace(tzinfo=timezone.utc)

            if thinking_since >= cutoff:
                continue

            lang = lead.get("lang", "en")
            message = self._generate_nudge_message("said they wanted to think it over 48+ hours ago", lang)
            if not message:
                continue

            if send_whatsapp_message(f"whatsapp:{phone}", message):
                with self._leads_lock:
                    lead["thinking_it_over_nudge_sent"] = True
                    self._save_leads()
