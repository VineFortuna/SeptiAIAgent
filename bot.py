from __future__ import annotations

import json
import os
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from notifications import send_staff_notification, send_whatsapp_message

BASE_DIR = Path(__file__).resolve().parent

EASTERN_TZ = ZoneInfo("America/New_York")
BUSINESS_HOURS_START = 7   # 7am Eastern
BUSINESS_HOURS_END = 21    # 9pm Eastern


def is_within_business_hours(now: datetime | None = None) -> bool:
    """7am-9pm, Eastern time (auto-adjusts for EST/EDT).

    DISABLE_BUSINESS_HOURS=true bypasses this entirely, for local demos/testing
    outside the real schedule without changing production behavior.
    """
    if os.getenv("DISABLE_BUSINESS_HOURS", "false").lower() == "true":
        return True

    current = (now or datetime.now(EASTERN_TZ)).astimezone(EASTERN_TZ)
    return BUSINESS_HOURS_START <= current.hour < BUSINESS_HOURS_END

# Longest-prefix match against E.164 calling codes -> which pricing bucket to quote.
# Starter list based on where the Sep7Ro diaspora audience is known to live; easy to
# extend as leads arrive from new countries.
COUNTRY_CODE_CURRENCY: dict[str, str] = {
    "44": "GBP",    # UK
    "1": "USD_CAN",  # US + Canada share the NANP "+1" prefix
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

# (prefix, suffix) used to format an amount for display, matching how each
# currency is written in Sep7Ro's own pricing sheet (e.g. "17 €", "£14", "67 RON").
CURRENCY_FORMAT: dict[str, tuple[str, str]] = {
    "EUR": ("", " €"),
    "GBP": ("£", ""),
    "USD_CAN": ("$", ""),
    "RON": ("", " RON"),
}

# Human-readable labels for each internal bucket — used in the AI prompt so the
# model never sees the internal "USD_CAN" code and writes it literally in replies.
CURRENCY_DISPLAY: dict[str, str] = {
    "EUR": "EUR",
    "GBP": "GBP",
    "USD_CAN": "USD / CAD",
    "RON": "RON",
}

REQUIRED_INTAKE_FIELDS: tuple[str, ...] = (
    "child_language_pref",
    "timezone",
    "child_age",
    "prior_experience",
    "availability_pref",
    "group_pref",
)

INTAKE_QUESTIONS: dict[str, dict[str, str]] = {
    "child_language_pref": {
        "en": "Does your child speak Romanian or English for class?",
        "ro": "Copilul vorbește română sau engleză pentru clasă?",
    },
    "timezone": {
        "en": "What time zone are you in?",
        "ro": "În ce fus orar sunteți?",
    },
    "child_age": {
        "en": "How old is your child?",
        "ro": "Câți ani are copilul?",
    },
    "prior_experience": {
        "en": "Has your child played chess before?",
        "ro": "A mai jucat șah copilul înainte?",
    },
    "availability_pref": {
        "en": "Would weekdays (afternoon/evening) or weekends work better for you?",
        "ro": "Vă e mai convenabil în timpul săptămânii (după-amiază/seară) sau în weekend?",
    },
    "group_pref": {
        "en": "Would your child prefer Exploratori (relaxed, curious) or Strategi (competitive, likes a challenge)?",
        "ro": "Copilul ar prefera Exploratori (relaxat, curios) sau Strategi (competitiv, iubește provocările)?",
    },
}

GREETING_INTRO: dict[str, list[str]] = {
    "en": [
        "Hey, Septi here from Sep7Ro! 🙂 Quick one before we line up a demo:",
        "Hi! Septi from Sep7Ro, just need 2 quick things from you:",
        "Hey, it's Septi 🙂 Got a sec for 2 quick questions?",
    ],
    "ro": [
        "Hey, Septi aici de la Sep7Ro! 🙂 Ceva rapid înainte de demo:",
        "Salut! Septi de la Sep7Ro, am nevoie de 2 lucruri rapide:",
        "Hey, sunt Septi 🙂 Ai un minut pentru 2 întrebări?",
    ],
}

CLOSING_MESSAGE: dict[str, list[str]] = {
    "en": [
        "Perfect, got it! 🙂 I'll line up some demo times and come back to you",
        "Awesome, thank you. Give me a bit, I'll follow up with some times",
        "Got it, thanks! 👍 Lining up a couple of demo slots now",
    ],
    "ro": [
        "Perfect, am notat! 🙂 Îți trimit niște variante de oră în scurt timp",
        "Super, mulțumesc. Revin cu câteva variante pentru demo",
        "Am notat, mersi! 👍 Pregătesc câteva ore pentru demo",
    ],
}

GREETING_REPLY: dict[str, list[str]] = {
    "en": [
        "Hey! 🙂 What's up?",
        "Hi! Septi here, how can I help?",
        "Hey there 😊 what can I do for you?",
        "Heyy 🙂",
    ],
    "ro": [
        "Hey! 🙂 Ce pot face pentru tine?",
        "Salut! Septi aici, cu ce te ajut?",
        "Hey, ce e? 😊",
        "Salut 🙂",
    ],
}

THANKS_REPLY: dict[str, list[str]] = {
    "en": [
        "Anytime! 🙂",
        "No worries at all 🙂",
        "Glad to help, shout if anything else comes up 😊",
        "Of course!",
    ],
    "ro": [
        "Cu plăcere! 🙂",
        "Sigur, oricând 🙂",
        "Mă bucur că ajut, dau un semn dacă mai e nevoie 😊",
        "Clar!",
    ],
}

HELP_REPLY: dict[str, list[str]] = {
    "en": [
        "Classes, pricing, booking a demo, your next lesson, ask away 🙂 Anything trickier and I'll personally dig into it",
        "Ask me anything, classes, pricing, demo booking. If it's something I need to check I'll follow up with you",
        "Pricing, classes, scheduling a demo, whatever you need, just ask 😊",
    ],
    "ro": [
        "Clase, prețuri, programare demo, lecția ta, întreabă liber 🙂 Dacă e ceva mai complicat, verific personal",
        "Întreabă orice, clase, prețuri, demo. Dacă e ceva ce trebuie verificat, revin eu",
        "Prețuri, clase, programare demo, orice ai nevoie, întreabă 😊",
    ],
}

HANDOFF_VARIANTS: dict[str, list[str]] = {
    "en": [
        "Hmm good question, lemme check and get back to you 🙂",
        "Not sure off the top of my head, give me a sec",
        "Let me dig into that one and I'll let you know 👍",
        "Don't know that off hand, checking now",
        "Good one, I'll find out and circle back to you 🙂",
    ],
    "ro": [
        "Hmm bună întrebare, las-mă să verific și-ți spun 🙂",
        "Nu știu pe loc, îmi dai un minut",
        "Las-mă să mă interesez și revin 👍",
        "Nu sunt sigur acum, verific și revin",
        "Bună întrebare, dau de capăt și-ți spun 🙂",
    ],
}

REGISTRATION_FALLBACK: dict[str, list[str]] = {
    "en": [
        "I'll sort you out myself, give me a bit and I'll come back with the details 🙂",
        "Let me handle that for you, I'll follow up shortly",
        "I'll take care of that, just give me a moment 👍",
    ],
    "ro": [
        "Te înscriu eu, îmi dai un moment și revin cu detaliile 🙂",
        "Mă ocup eu de asta, revin în scurt timp",
        "Las-mă să rezolv eu asta, revin imediat 👍",
    ],
}

REGISTRATION_LINK_REPLY: dict[str, list[str]] = {
    "en": [
        "Yes! You can sign up right here: {link} 🙂",
        "Sure thing, here's the link: {link}",
        "Here you go: {link} 👍",
    ],
    "ro": [
        "Da, sigur! Te poți înscrie aici: {link} 🙂",
        "Clar, aici e linkul: {link}",
        "Poftim: {link} 👍",
    ],
}

BOOKING_FOUND: dict[str, list[str]] = {
    "en": [
        "Your next {class_name} is on {date} at {time} 🙂",
        "You're booked for {class_name} on {date} at {time}",
    ],
    "ro": [
        "Următoarea ta lecție, {class_name}, e pe {date} la ora {time} 🙂",
        "Ești programat la {class_name} pe {date}, ora {time}",
    ],
}

BOOKING_NOT_FOUND: dict[str, list[str]] = {
    "en": [
        "Hmm, not seeing a booking on this number, what name did you book under?",
        "Can't match this number to a booking, send me the name you used and I'll find it",
        "Don't see anything under this number 🤔 what name should I look for?",
    ],
    "ro": [
        "Hmm, nu găsesc o rezervare pe acest număr, ce nume ai folosit?",
        "Nu văd nimic pe numărul ăsta, trimite-mi numele de pe rezervare",
        "Nu apare nimic pe acest număr 🤔 ce nume să caut?",
    ],
}

CURRENCY_DEFAULT_NOTE = {
    "en": "I'll quote prices in EUR, let me know if you'd like a different currency",
    "ro": "Voi da prețurile în EUR, spune-mi dacă preferi altă moneda",
}

GROUP_LISTING_SINGLE: dict[str, list[str]] = {
    "en": [
        "Right now I've got {joined} running 🙂",
        "Just {joined} active at the moment",
        "{joined} is the one running right now 👍",
    ],
    "ro": [
        "Acum am grupa {joined} activă 🙂",
        "Momentan doar grupa {joined} e activă",
        "Grupa {joined} e cea activă acum 👍",
    ],
}

GROUP_LISTING_MULTI: dict[str, list[str]] = {
    "en": [
        "Right now I've got {joined} running 🙂",
        "I've got {joined} going at the moment",
        "{joined} are both active right now 👍",
    ],
    "ro": [
        "Acum am grupele {joined} active 🙂",
        "Momentan am grupele {joined} active",
        "Grupele {joined} sunt active acum 👍",
    ],
}

# Keyword hints used only to *route* a message to the AI knowledge-base path
# during lead intake (so "how much does it cost" mid-intake gets answered for
# real instead of being captured as an intake answer). Not used for answering.
AI_TOPIC_HINTS: tuple[str, ...] = (
    "price", "cost", "pret", "preț", "cat costa", "câtă costă", "discount", "reducere",
    "lichess", "online account", "cont online",
    "tournament", "turneu",
    "review", "recenzi", "benefits", "beneficii", "teachers", "profesori",
)


def infer_currency_bucket(phone: str) -> tuple[str, str | None]:
    """Infer which pricing bucket to quote from an E.164 phone number's calling code."""
    digits = re.sub(r"[^0-9]", "", phone)

    for length in (3, 2, 1):
        prefix = digits[:length]

        if prefix in COUNTRY_CODE_CURRENCY:
            return COUNTRY_CODE_CURRENCY[prefix], prefix

    return DEFAULT_CURRENCY_BUCKET, None


def format_money(amount: str, currency_bucket: str) -> str:
    prefix, suffix = CURRENCY_FORMAT.get(currency_bucket, ("", f" {currency_bucket}"))
    return f"{prefix}{amount}{suffix}"


RO_WORD_MARKERS: tuple[str, ...] = (
    "salut", "buna", "bună", "multumesc", "mulțumesc", "copil", "vreau",
    "pentru", "sunt", "fiul", "fiica", "lectie", "lecție", "sah", "șah",
    "este", "cum", "unde", "cand", "când", "cat", "cât", "daca", "dacă",
    "asta", "ceva", "avem", "aveti", "aveți", "cati", "câți", "joaca",
    # "are" is ambiguous (EN "are" vs RO "are" = "has") - listed in both
    # marker sets so it cancels out rather than always tipping to English.
    "are", "nevoie", "trebuie", "poate", "mereu", "acum", "mea", "meu",
)
EN_WORD_MARKERS: tuple[str, ...] = (
    "hello", "hi", "hey", "thanks", "please", "child", "son", "daughter",
    "interested", "lesson", "want", "the", "you", "your", "can", "what",
    "how", "do", "does", "is", "are", "my", "this", "that", "with", "for",
    "accept", "offer", "need", "have", "much", "many",
)


def detect_language(text: str) -> str:
    """Light heuristic: Romanian diacritics win outright, otherwise whichever
    language's whole-word markers appear more often, defaulting to Romanian
    on a tie (primary audience)."""
    lowered = text.lower()

    if any(char in lowered for char in "ăâîșț"):
        return "ro"

    ro_hits = sum(1 for marker in RO_WORD_MARKERS if re.search(rf"\b{marker}\b", lowered))
    en_hits = sum(1 for marker in EN_WORD_MARKERS if re.search(rf"\b{marker}\b", lowered))

    return "en" if en_hits > ro_hits else "ro"


class ClassAssistant:
    def __init__(
        self,
        leads_path: Path | None = None,
        notifier: Callable[[str], bool] | None = None,
        pending_path: Path | None = None,
        customer_notifier: Callable[[str, str], bool] | None = None,
    ) -> None:
        self.company_data = self._load_json("company_data.json")
        self.bookings = self._load_json("bookings.json")

        self.leads_path = leads_path or (BASE_DIR / "leads.json")
        self.leads = self._load_leads(self.leads_path)
        self.notifier = notifier or send_staff_notification
        self._last_pick: dict[Any, str] = {}

        self.pending_path = pending_path or (BASE_DIR / "pending_messages.json")
        self.pending: dict[str, list[dict[str, str]]] = self._load_leads(self.pending_path)
        self.customer_notifier = customer_notifier or send_whatsapp_message

        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model = os.getenv("OPENAI_MODEL", "gpt-5.5").strip()
        self.ai_enabled = bool(self.api_key)
        self.client = None
        self._conversation_history: dict[str, list[dict[str, str]]] = {}

        if self.ai_enabled:
            from openai import OpenAI

            self.client = OpenAI(api_key=self.api_key)

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
        with self.leads_path.open("w", encoding="utf-8") as file:
            json.dump(self.leads, file, ensure_ascii=False, indent=2)

    def _save_pending(self) -> None:
        with self.pending_path.open("w", encoding="utf-8") as file:
            json.dump(self.pending, file, ensure_ascii=False, indent=2)

    def queue_message(self, message: str, sender_phone: str) -> None:
        """Store an off-hours message to be answered once business hours resume."""
        phone = self._normalize_phone(sender_phone)
        entry = {
            "message": message,
            "sender_phone": sender_phone,
            "received_at": datetime.now(timezone.utc).isoformat(),
        }
        self.pending.setdefault(phone, []).append(entry)
        self._save_pending()

    def process_pending_messages(self) -> None:
        """Answer queued off-hours messages, but only once business hours are open."""
        if not is_within_business_hours():
            return

        for phone, queued in list(self.pending.items()):
            remaining = []

            for entry in queued:
                if "reply_text" not in entry:
                    entry["reply_text"] = self.reply(entry["message"], entry["sender_phone"])
                sent = self.customer_notifier(entry["sender_phone"], entry["reply_text"])

                if not sent:
                    remaining.append(entry)

            if remaining:
                self.pending[phone] = remaining
            else:
                del self.pending[phone]

        self._save_pending()

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        return re.sub(r"[^0-9+]", "", phone)

    @staticmethod
    def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
        return any(phrase in text for phrase in phrases)

    @staticmethod
    def _is_missing(value: Any) -> bool:
        if value is None:
            return True

        text = str(value).strip()
        return not text or "REPLACE" in text.upper()

    def _pick_no_repeat(self, key: Any, variants: list[str]) -> str:
        """Pick a random variant, never repeating whatever was picked last for this key."""
        last = self._last_pick.get(key)
        choices = [v for v in variants if v != last] if len(variants) > 1 else variants
        chosen = random.choice(choices)
        self._last_pick[key] = chosen
        return chosen

    def _pick(self, pool: dict[str, list[str]], lang: str) -> str:
        variants = pool.get(lang) or pool.get("ro") or next(iter(pool.values()))
        return self._pick_no_repeat((id(pool), lang), variants)

    def _value(self, key: str, lang: str = "ro") -> str | None:
        value = self.company_data.get(key)

        if isinstance(value, dict):
            primary = value.get(lang)
            fallback = value.get("en" if lang == "ro" else "ro")
            value = primary if not self._is_missing(primary) else fallback

        if isinstance(value, list):
            candidates = [item for item in value if not self._is_missing(item)]

            if not candidates:
                return None

            return self._pick_no_repeat((key, lang), candidates).strip()

        if self._is_missing(value):
            return None

        return str(value).strip()

    def _handoff(self, lang: str = "ro") -> str:
        return self._pick(HANDOFF_VARIANTS, lang)

    def _fact(self, key: str, lang: str = "ro") -> str:
        value = self._value(key, lang)

        if not value:
            return self._handoff(lang)

        return value

    def _registration_reply(self, lang: str = "ro") -> str:
        link = self._value("registration_link")

        if not link:
            return self._pick(REGISTRATION_FALLBACK, lang)

        return self._pick(REGISTRATION_LINK_REPLY, lang).format(link=link)

    def _booking_reply(self, sender_phone: str, lang: str = "ro") -> str:
        phone = self._normalize_phone(sender_phone)
        booking = self.bookings.get(phone)

        if not booking:
            return self._pick(BOOKING_NOT_FOUND, lang)

        class_name = booking.get("class_name", "class")
        date = booking.get("date", "the scheduled date")
        time = booking.get("time", "the scheduled time")

        reply = self._pick(BOOKING_FOUND, lang).format(class_name=class_name, date=date, time=time)

        location = booking.get("location")
        if location:
            suffix = ", la {location}" if lang == "ro" else ", at {location}"
            reply += suffix.format(location=location)

        return reply

    def _bilingual(self, value: Any, lang: str, pick_one: bool = False) -> str | None:
        if not isinstance(value, dict):
            return None

        primary = value.get(lang)
        fallback = value.get("en" if lang == "ro" else "ro")
        chosen = primary if not self._is_missing(primary) else fallback

        if self._is_missing(chosen):
            return None

        if isinstance(chosen, list):
            if pick_one:
                return self._pick_no_repeat((id(value), lang), chosen).strip()

            return "; ".join(str(item) for item in chosen)

        return str(chosen).strip()

    def _mentions_ai_topic(self, text: str) -> bool:
        return self._contains_any(text, AI_TOPIC_HINTS)

    def _get_lead(self, phone: str) -> dict[str, Any] | None:
        return self.leads.get(phone)

    def _create_lead(self, phone: str, lang: str) -> dict[str, Any]:
        currency_bucket, country_code = infer_currency_bucket(phone)
        now = datetime.now(timezone.utc).isoformat()

        lead = {
            "stage": "intake_in_progress",
            "lang": lang,
            "currency_bucket": currency_bucket,
            "country_calling_code": country_code,
            "collected_fields": [],
            "handed_off": False,
            "created_at": now,
            "updated_at": now,
        }

        for field in REQUIRED_INTAKE_FIELDS:
            lead[field] = None

        self.leads[phone] = lead
        return lead

    def _next_missing_field(self, lead: dict[str, Any]) -> str | None:
        collected = lead.get("collected_fields", [])

        for field in REQUIRED_INTAKE_FIELDS:
            if field not in collected:
                return field

        return None

    def _normalize_intake_answer(self, field: str, text: str) -> str:
        lowered = text.lower().strip()

        if field == "child_language_pref":
            if self._contains_any(lowered, ("romana", "română", "romanian")):
                return "ro"
            if self._contains_any(lowered, ("engleza", "engleză", "english")):
                return "en"
        elif field == "availability_pref":
            has_weekday = self._contains_any(lowered, ("saptamana", "săptămână", "weekday"))
            has_weekend = "weekend" in lowered
            if has_weekday and has_weekend:
                return "both"
            if has_weekday:
                return "weekday"
            if has_weekend:
                return "weekend"
        elif field == "group_pref":
            if "explorator" in lowered:
                return "exploratori"
            if "strateg" in lowered:
                return "strategi"

        return text.strip()

    def _store_intake_answer(self, lead: dict[str, Any], field: str, text: str) -> None:
        lead[field] = self._normalize_intake_answer(field, text)
        lead.setdefault("collected_fields", []).append(field)
        lead["updated_at"] = datetime.now(timezone.utc).isoformat()

    def _maybe_notify_staff(self, phone: str, lead: dict[str, Any]) -> None:
        lang = lead.get("lang", "ro")
        labels = {
            "child_language_pref": ("Child's class language", "Limba clasei pentru copil"),
            "timezone": ("Time zone", "Fus orar"),
            "child_age": ("Child's age", "Vârsta copilului"),
            "prior_experience": ("Prior chess experience", "Experiență anterioară la șah"),
            "availability_pref": ("Availability", "Disponibilitate"),
            "group_pref": ("Group preference", "Preferință grupă"),
        }
        header = "New chess lead" if lang == "en" else "Lead nou la sah"
        lines = [f"{header}: {phone}", f"Currency: {lead.get('currency_bucket')}"]

        for field in REQUIRED_INTAKE_FIELDS:
            label = labels[field][0 if lang == "en" else 1]
            lines.append(f"{label}: {lead.get(field) or '-'}")

        self.notifier("\n".join(lines))

    def _handle_lead_intake(self, message: str, phone: str) -> str | None:
        if phone in self.bookings:
            return None

        lead = self._get_lead(phone)

        if lead is not None and lead.get("stage") == "faq_only":
            return None

        if lead is None:
            lang = detect_language(message)
            faq_answer = self._rule_based_reply(message, phone)
            lead = self._create_lead(phone, lang)
            question = INTAKE_QUESTIONS[REQUIRED_INTAKE_FIELDS[0]][lang]
            self._save_leads()

            intro = f"{self._pick(GREETING_INTRO, lang)} {question}"

            all_greetings = [v for variants in GREETING_REPLY.values() for v in variants]
            is_redundant_greeting = faq_answer in all_greetings

            if faq_answer and not is_redundant_greeting:
                return f"{faq_answer}\n\n{intro}"

            return intro

        lang = lead.get("lang", "ro")

        if self._rule_based_reply(message, phone) or self._mentions_ai_topic(message):
            return None

        pending_field = self._next_missing_field(lead)

        if pending_field is None:
            return None

        self._store_intake_answer(lead, pending_field, message)
        next_field = self._next_missing_field(lead)

        if next_field is not None:
            self._save_leads()
            return INTAKE_QUESTIONS[next_field][lang]

        lead["stage"] = "faq_only"
        lead["handed_off"] = True
        self._save_leads()
        self._maybe_notify_staff(phone, lead)
        return self._pick(CLOSING_MESSAGE, lang)

    def _list_classes(self, lang: str = "ro") -> str:
        groups = self.company_data.get("groups", {})

        names = [
            self._bilingual(details.get("display_name"), lang) or group_key.title()
            for group_key, details in groups.items()
        ]

        if not names:
            return self._handoff(lang)

        conjunction = "și" if lang == "ro" else "and"
        joined = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} {conjunction} {names[-1]}"
        pool = GROUP_LISTING_SINGLE if len(names) == 1 else GROUP_LISTING_MULTI

        return self._pick(pool, lang).format(joined=joined)

    def _rule_based_reply(
        self,
        message: str,
        sender_phone: str,
    ) -> str | None:
        text = message.lower().strip()
        lang = detect_language(message)

        if not text:
            return self._pick(GREETING_REPLY, lang)

        greetings = {
            "hi",
            "hello",
            "hey",
            "good morning",
            "good afternoon",
            "good evening",
            "salut",
            "buna",
            "bună",
            "buna ziua",
            "bună ziua",
            "servus",
        }

        if text in greetings:
            return self._pick(GREETING_REPLY, lang)

        if self._contains_any(
            text,
            ("thank you", "thanks", "thx", "multumesc", "mulțumesc", "mersi"),
        ):
            return self._pick(THANKS_REPLY, lang)

        if self._contains_any(
            text,
            (
                "what can you do",
                "what can i ask",
                "help",
                "ce poti face",
                "ce pot intreba",
                "ajutor",
            ),
        ):
            return self._pick(HELP_REPLY, lang)

        if self._contains_any(
            text,
            (
                "human",
                "staff",
                "real person",
                "manager",
                "complaint",
                "refund",
                "emergency",
                "om real",
                "vorbesc cu o persoana",
                "reclamatie",
                "reclamație",
                "rambursare",
                "urgenta",
                "urgență",
            ),
        ):
            return self._handoff(lang)

        if self._contains_any(
            text,
            (
                "sign up",
                "signup",
                "register",
                "registration",
                "enroll",
                "book a class",
                "join a class",
                "ma inscriu",
                "mă înscriu",
                "inscriere",
                "înscriere",
                "cum ma inscriu",
                "cum mă înscriu",
            ),
        ):
            return self._registration_reply(lang)

        if self._contains_any(
            text,
            (
                "my class",
                "my next class",
                "when do i start",
                "when does my",
                "what time is my",
                "when am i booked",
                "my booking",
                "my appointment",
                "clasa mea",
                "lectia mea",
                "lecția mea",
                "cand am clasa",
                "când am clasa",
                "cand incep",
                "când începem",
            ),
        ):
            return self._booking_reply(sender_phone, lang)

        if self._contains_any(
            text,
            (
                "what classes",
                "which classes",
                "classes do you offer",
                "types of classes",
                "class options",
                "what groups",
                "which groups",
                "groups do you offer",
                "ce clase",
                "ce grupe",
                "ce grupe aveti",
                "ce grupe aveți",
            ),
        ):
            return self._list_classes(lang)

        if self._contains_any(
            text,
            (
                "how long are the classes",
                "class duration",
                "class lengths",
                "how long is a lesson",
                "cat dureaza",
                "cât durează",
                "durata lectiei",
                "durata lecției",
            ),
        ):
            return self._bilingual(self.company_data.get("class_duration"), lang, pick_one=True) or self._handoff(lang)

        faq_rules: list[tuple[tuple[str, ...], str]] = [
            (
                (
                    "class schedule",
                    "class times",
                    "what days",
                    "what times",
                    "when are classes",
                    "orarul claselor",
                    "ce zile",
                    "ce ore",
                    "cand sunt clasele",
                    "când sunt clasele",
                ),
                "class_schedule",
            ),
            (
                (
                    "where are you",
                    "location",
                    "address",
                    "where is the class",
                    "unde sunteti",
                    "unde sunteți",
                    "adresa",
                    "unde este clasa",
                ),
                "location",
            ),
            (
                (
                    "business hours",
                    "opening hours",
                    "what time do you open",
                    "what time do you close",
                    "are you open",
                    "program de lucru",
                    "ce program aveti",
                    "ce program aveți",
                    "sunteti deschisi",
                    "sunteți deschiși",
                ),
                "business_hours",
            ),
            (
                (
                    "what should i bring",
                    "what do i bring",
                    "need to bring",
                    "ce trebuie sa aduc",
                    "ce trebuie să aduc",
                    "ce aduc",
                ),
                "what_to_bring",
            ),
            (
                (
                    "what should i wear",
                    "what do i wear",
                    "dress code",
                    "clothing",
                    "ce trebuie sa porte",
                    "ce trebuie să poarte",
                    "ce sa imbrace",
                    "ce să îmbrace",
                    "ce trebuie sa port",
                    "ce trebuie să port",
                    "ce sa poarte",
                    "ce să poarte",
                ),
                "what_to_wear",
            ),
            (
                (
                    "age requirement",
                    "minimum age",
                    "how old",
                    "age limit",
                    "kids",
                    "children",
                    "varsta minima",
                    "vârsta minimă",
                    "de la ce varsta",
                    "de la ce vârstă",
                    "cati ani",
                    "câți ani",
                ),
                "age_requirements",
            ),
            (
                (
                    "need experience",
                    "no experience",
                    "beginner friendly",
                    "never done",
                    "first time",
                    "are nevoie de experienta",
                    "are nevoie de experiență",
                    "nu a mai jucat",
                    "e incepator",
                    "e începător",
                ),
                "experience_required",
            ),
            (
                (
                    "how early",
                    "when should i arrive",
                    "arrival time",
                    "cu cat timp inainte",
                    "cu cât timp înainte",
                    "cand ne conectam",
                    "când ne conectăm",
                ),
                "arrival_time",
            ),
            (
                (
                    "public transit",
                    "bus",
                    "subway",
                    "train",
                    "transit",
                    "transport in comun",
                    "transport în comun",
                    "autobuz",
                ),
                "public_transit_information",
            ),
            (
                (
                    "accessible",
                    "accessibility",
                    "wheelchair",
                    "accesibilitate",
                    "scaun cu rotile",
                ),
                "accessibility_information",
            ),
            (
                (
                    "cancel",
                    "cancellation",
                    "anulare",
                    "anulez",
                    "politica de anulare",
                ),
                "cancellation_policy",
            ),
            (
                (
                    "reschedule",
                    "change my class",
                    "move my class",
                    "reprogramare",
                    "reprogramez",
                    "schimb ora",
                ),
                "rescheduling_policy",
            ),
            (
                (
                    "running late",
                    "late arrival",
                    "miss the start",
                    "intarziem",
                    "întârziem",
                    "ajung mai tarziu",
                    "ajung mai târziu",
                ),
                "late_arrival_policy",
            ),
            (
                (
                    "payment",
                    "pay",
                    "credit card",
                    "debit",
                    "cash",
                    "plata",
                    "plată",
                    "cum platesc",
                    "cum plătesc",
                    "card",
                ),
                "payment_methods",
            ),
            (
                (
                    "trial class",
                    "free trial",
                    "try a class",
                    "lectie demo",
                    "lecție demo",
                    "lectie gratuita",
                    "lecție gratuită",
                    "demo gratuit",
                ),
                "trial_class_policy",
            ),
            (
                (
                    "drop in",
                    "drop-in",
                    "walk in",
                    "walk-in",
                    "fara abonament",
                    "fără abonament",
                    "o singura data",
                    "o singură dată",
                ),
                "drop_in_policy",
            ),
            (
                (
                    "private lesson",
                    "private class",
                    "one on one",
                    "one-on-one",
                    "lectie privata",
                    "lecție privată",
                    "ore individuale",
                ),
                "private_lessons",
            ),
            (
                (
                    "group size",
                    "class size",
                    "how many people",
                    "how many students",
                    "cati copii",
                    "câți copii",
                    "marimea grupei",
                    "mărimea grupei",
                ),
                "group_size",
            ),
            (
                (
                    "waitlist",
                    "waiting list",
                    "lista de asteptare",
                    "lista de așteptare",
                ),
                "waitlist_policy",
            ),
            (
                (
                    "spots available",
                    "space available",
                    "availability",
                    "is there room",
                    "class full",
                    "mai sunt locuri",
                    "locuri disponibile",
                    "mai e loc",
                ),
                "class_availability_message",
            ),
            (
                (
                    "phone number",
                    "call you",
                    "contact number",
                    "numar de telefon",
                    "număr de telefon",
                    "va pot suna",
                    "vă pot suna",
                ),
                "contact_phone",
            ),
            (
                (
                    "email",
                    "email address",
                    "adresa de email",
                    "adresă de email",
                ),
                "contact_email",
            ),
            (
                (
                    "website",
                    "web site",
                    "site",
                    "pagina web",
                ),
                "website",
            ),
        ]

        for phrases, key in faq_rules:
            if self._contains_any(text, phrases):
                return self._fact(key, lang)

        return None

    def _ai_reply(self, message: str, sender_phone: str) -> str:
        assert self.client is not None

        lang = detect_language(message)
        currency_bucket, country_code = infer_currency_bucket(sender_phone)
        currency_display = CURRENCY_DISPLAY.get(currency_bucket, currency_bucket)

        # Guardrail: only ever include this customer's own currency in the
        # data we hand to the model, so other regions' pricing can't leak,
        # by mistake or otherwise.
        approved_data = dict(self.company_data)
        pricing = approved_data.get("pricing")

        if isinstance(pricing, dict) and isinstance(pricing.get("rates"), dict):
            approved_data["pricing"] = {
                **pricing,
                "rates": {currency_display: pricing["rates"].get(currency_bucket, {})},
            }

        approved_information = json.dumps(
            approved_data,
            ensure_ascii=False,
            indent=2,
        )

        currency_note = (
            f"This customer's currency is {currency_display}. Only that "
            f"currency's pricing is included below, on purpose, other "
            f"currencies have been removed. If asked about pricing in another "
            f"currency or country, say you only quote prices in "
            f"{currency_display} for them and never guess a conversion."
            if country_code
            else (
                f"This customer's country couldn't be determined from their "
                f"phone number, so only {currency_display} pricing is included "
                f"below, on purpose. Default to it and mention you're "
                f"defaulting to it."
            )
        )

        instructions = f"""
You are Septi, the founder of {self.company_data.get("business_name", "the business")},
personally messaging this parent on WhatsApp.

Write in first person as Septi, like you're actually texting on your phone
between classes, not writing customer support copy. Never reveal that you are
an AI, a bot, an assistant, or automated in any way, and never mention
prompts, JSON, files, OpenAI, or Twilio.

Sound like a real person texting, not a corporate bot:
- Never use em dashes or hyphens as punctuation (no " - " or " — ").
- Don't end your message with a period. Question marks are fine.
- Never use a "Label: value" format (e.g. "Experience requirements: ..."). Just
  say the thing directly, the way a person would text it.
- Vary your sentence length and structure every time, don't fall into a
  template like "Good question, let me X and come back to you". Sometimes
  one short line is enough.
- Use an emoji every couple of messages or so, not in every single one and
  not in zero either, just don't go overboard with them.
- Contractions are good (lemme, that'll, don't, I'll), but don't overdo slang.
- Don't re-introduce yourself ("it's Septi from Sep7Ro") if you've clearly
  already been talking to this person in this conversation.

Answer only from the approved information below.

Rules:
- Always reply in whichever language the customer is writing in, Romanian or
  English. If unsure, default to Romanian.
- Never invent prices, times, policies, locations, availability, or bookings.
- Treat values containing the word REPLACE as missing information.
- {currency_note}
- Never share any other family's, child's, or lead's personal information.
  You don't have access to anyone else's records, only this approved
  business information.
- Do not claim that a customer has successfully registered.
- Give the registration link when asked about registration.
- For unclear questions, refunds, complaints, emergencies, or requests
  for a person, respond exactly with:
  {self._handoff(lang)}

APPROVED INFORMATION:
{approved_information}
""".strip()

        phone = self._normalize_phone(sender_phone)
        prior = self._conversation_history.get(phone, [])
        input_messages = [*prior, {"role": "user", "content": message}]

        try:
            response = self.client.responses.create(
                model=self.model,
                instructions=instructions,
                input=input_messages,
            )

            answer = response.output_text.strip()
            return answer or self._handoff(lang)

        except Exception:
            return self._handoff(lang)

    def reply(self, message: str, sender_phone: str) -> str:
        phone = self._normalize_phone(sender_phone)

        intake_reply = self._handle_lead_intake(message, phone)
        if intake_reply is not None:
            reply_text = intake_reply
        else:
            rule_reply = self._rule_based_reply(message, sender_phone)
            if rule_reply:
                reply_text = rule_reply
            elif self.ai_enabled:
                reply_text = self._ai_reply(message, sender_phone)
            else:
                reply_text = self._handoff(detect_language(message))

        history = self._conversation_history.setdefault(phone, [])
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": reply_text})
        if len(history) > 20:
            self._conversation_history[phone] = history[-20:]

        return reply_text