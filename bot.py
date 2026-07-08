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

# (prefix, suffix) used to format an amount for display, matching how each
# currency is written in Sep7Ro's own pricing sheet (e.g. "17 €", "£14", "67 RON").
CURRENCY_FORMAT: dict[str, tuple[str, str]] = {
    "EUR": ("", " €"),
    "GBP": ("£", ""),
    "USD": ("$", ""),
    "CAD": ("$", " CAD"),
    "RON": ("", " RON"),
}

# Human-readable labels for each bucket — used in the AI prompt so the model
# writes the currency name correctly in replies.
CURRENCY_DISPLAY: dict[str, str] = {
    "EUR": "EUR",
    "GBP": "GBP",
    "USD": "USD",
    "CAD": "CAD",
    "RON": "RON",
}

CONSTRAINED_FIELD_VALUES: dict[str, frozenset[str]] = {
    "child_language_pref": frozenset({"ro", "en"}),
    "group_pref": frozenset({"exploratori", "strategi"}),
}

REQUIRED_INTAKE_FIELDS: tuple[str, ...] = (
    "country",
    "child_language_pref",
    "timezone",
    "child_age",
    "prior_experience",
    "availability_pref",
    "school_dismissal",
    "group_pref",
    "extra_notes",
)

INTAKE_QUESTIONS: dict[str, dict[str, str]] = {
    "country": {
        "en": "What country are you in?",
        "ro": "Din ce țară ești?",
    },
    "child_language_pref": {
        "en": "What languages can your child speak?",
        "ro": "Ce limbi vorbește copilul?",
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
        "en": "Which days work best for your child? Weekdays, weekends, specific days, whatever works 🙂",
        "ro": "Ce zile funcționează cel mai bine? Zile de lucru, weekend, zile specifice, orice e bine 🙂",
    },
    "school_dismissal": {
        "en": "And roughly what time do they get home from school, or when are they generally free to start?",
        "ro": "Și cam la ce oră ajunge acasă de la școală, sau de când e liber să înceapă?",
    },
    "group_pref": {
        "en": "Would your child prefer Exploratori (relaxed, curious) or Strategi (competitive, likes a challenge)?",
        "ro": "Copilul ar prefera Exploratori (relaxat, curios) sau Strategi (competitiv, iubește provocările)?",
    },
    "extra_notes": {
        "en": "Anything else you'd like Septi to know before he reaches out?",
        "ro": "Mai este ceva ce ați vrea să știe Septi înainte să vă contacteze?",
    },
}

GREETING_INTRO: dict[str, list[str]] = {
    "en": [
        "Hey! I'm Septi's assistant at Sep7Ro 🙂 How can I help you?",
        "Hi there! I'm the assistant here at Sep7Ro, how can I help?",
        "Hey, I'm Septi's assistant from Sep7Ro! What can I do for you?",
    ],
    "ro": [
        "Bună! Sunt asistenta lui Septi la Sep7Ro 🙂 Cu ce te pot ajuta?",
        "Salut! Sunt asistenta de la Sep7Ro, cu ce te ajut?",
        "Hey, sunt asistenta lui Septi de la Sep7Ro! Cu ce pot ajuta?",
    ],
}

CLOSING_MESSAGE: dict[str, list[str]] = {
    "en": [
        "Perfect, got everything I need! 🙂 Septi will reach out to you soon with some available class times",
        "Awesome, thank you! Septi will follow up with you directly with some demo slots",
        "Got it, thanks! 👍 Septi will get in touch soon with available times for your child",
    ],
    "ro": [
        "Perfect, am notat tot! 🙂 Septi te va contacta în curând cu niște variante de oră",
        "Super, mulțumesc! Septi îți va scrie direct cu câteva variante pentru demo",
        "Am notat, mersi! 👍 Septi te contactează în curând cu orele disponibile",
    ],
}

GREETING_REPLY: dict[str, list[str]] = {
    "en": [
        "Hey! 🙂 What's up?",
        "Hi! How can I help?",
        "Hey there 😊 what can I do for you?",
        "Heyy 🙂",
    ],
    "ro": [
        "Hey! 🙂 Ce pot face pentru tine?",
        "Salut! Cu ce te ajut?",
        "Hey, ce e? 😊",
        "Salut 🙂",
    ],
}

UNCLEAR_INPUT: dict[str, list[str]] = {
    "en": [
        "Sorry, didn't quite get that 😊 What did you want to know?",
        "Hmm, didn't catch that. What can I help you with?",
        "Not sure I followed, feel free to ask anything 🙂",
    ],
    "ro": [
        "Hmm, nu am înțeles bine 😊 Cu ce te pot ajuta?",
        "Nu am prins, spune-mi cu ce pot ajuta 🙂",
        "Nu prea am înțeles, ce ai vrea să știi?",
    ],
}

INTAKE_TRANSITION: dict[str, list[str]] = {
    "en": [
        "Happy to help! What country are you in?",
        "Of course! Before I get into that, what country are you based in?",
        "Sure thing! Just one quick question, what country are you in?",
    ],
    "ro": [
        "Cu plăcere! Din ce țară ești?",
        "Sigur! Înainte să îți răspund, din ce țară ești?",
        "Clar! O singură întrebare rapidă, din ce țară ești?",
    ],
}

INTAKE_ACK: dict[str, list[str]] = {
    "en": [
        "Got it!",
        "Nice!",
        "Perfect!",
        "Great, thanks!",
        "Awesome!",
    ],
    "ro": [
        "Am înțeles!",
        "Super!",
        "Perfect!",
        "Bine, mulțumesc!",
        "Excelent!",
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

    # +1 covers both US and Canada; use the 3-digit area code to tell them apart.
    if digits and digits[0] == "1":
        area_code = digits[1:4] if len(digits) >= 4 else ""
        return ("CAD", "1") if area_code in CANADIAN_AREA_CODES else ("USD", "1")

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
    "when", "i", "class", "time", "book", "booked", "who", "where",
    "like", "would", "love", "just", "also", "know", "about", "could",
    "should", "get", "it", "sign", "up", "id", "let", "tell", "more",
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
        history_path: Path | None = None,
    ) -> None:
        self.company_data = self._load_json("company_data.json")
        self.bookings = self._load_leads(BASE_DIR / "bookings.json")

        self.leads_path = leads_path or (BASE_DIR / "leads.json")
        self.leads = self._load_leads(self.leads_path)
        self.notifier = notifier or send_staff_notification
        self._last_pick: dict[Any, str] = {}

        self.pending_path = pending_path or (BASE_DIR / "pending_messages.json")
        self.pending: dict[str, list[dict[str, str]]] = self._load_leads(self.pending_path)
        self.customer_notifier = customer_notifier or send_whatsapp_message

        self.history_path = history_path or (BASE_DIR / "conversation_history.json")
        self._conversation_history: dict[str, list[dict[str, str]]] = self._load_leads(self.history_path)

        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model = os.getenv("OPENAI_MODEL", "gpt-5.5").strip()
        self.ai_enabled = bool(self.api_key)
        self.client = None

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

    def _save_history(self) -> None:
        with self.history_path.open("w", encoding="utf-8") as file:
            json.dump(self._conversation_history, file, ensure_ascii=False, indent=2)

    @staticmethod
    def _infer_currency_from_country(country_text: str) -> str | None:
        """Map a free-text country answer to a pricing bucket, or None if unknown."""
        lowered = country_text.lower()
        if any(w in lowered for w in ("romania", "românia", "roman")):
            return "RON"
        if any(w in lowered for w in ("moldova", "moldov")):
            return "RON"
        if any(w in lowered for w in ("uk", "united kingdom", "england", "britain", "scotland", "wales")):
            return "GBP"
        if any(w in lowered for w in ("canada", "canadian")):
            return "CAD"
        if any(w in lowered for w in ("usa", "united states", "america")):
            return "USD"
        euro_countries = (
            "germany", "german", "deutschland",
            "france", "french", "franța", "franta",
            "italy", "italian", "italia",
            "spain", "spanish", "spania",
            "netherlands", "dutch", "olanda",
            "belgium", "belgian", "belgia",
            "austria", "österreich",
            "portugal", "portuguese", "portugalia",
            "ireland", "irish", "irlanda",
            "greece", "greek", "grecia",
            "luxembourg", "luxemburg",
        )
        if any(w in lowered for w in euro_countries):
            return "EUR"
        return None

    def _try_extract_field(self, field: str, message: str) -> str | None:
        """Try to pull an answer for `field` from a message without explicitly asking.

        Only attempted for constrained-value fields (language/availability/group) and
        age — timezone and prior_experience are too open-ended for silent extraction.
        Returns the normalized value on a confident signal, None otherwise.
        """
        if field in CONSTRAINED_FIELD_VALUES:
            normalized = self._normalize_intake_answer(field, message)
            return normalized if normalized in CONSTRAINED_FIELD_VALUES[field] else None

        if field == "child_age":
            lowered = message.lower()
            half = re.search(
                r"\b(\d+)\s+(?:and\s+a\s+half|și\s+(?:o\s+)?jumătate)\b", lowered
            )
            if half:
                val = int(half.group(1)) + 0.5
                if 3 <= val < 18:
                    return str(val)
            m = re.search(r"\b(\d+)\s*(?:ani?|years?\s*old|yo)\b", lowered)
            if m and 3 <= int(m.group(1)) <= 17:
                return m.group(1)

        return None

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
                if "reply_parts" not in entry:
                    entry["reply_parts"] = self.reply(entry["message"], entry["sender_phone"])
                sent = all(
                    self.customer_notifier(entry["sender_phone"], part)
                    for part in entry["reply_parts"]
                )
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

    def _create_lead(self, phone: str, lang: str, initial_stage: str = "intake_in_progress") -> dict[str, Any]:
        currency_bucket, country_code = infer_currency_bucket(phone)
        now = datetime.now(timezone.utc).isoformat()

        lead = {
            "stage": initial_stage,
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
            has_ro = self._contains_any(lowered, ("romana", "română", "romanian"))
            has_en = self._contains_any(lowered, ("engleza", "engleză", "english"))
            if has_ro and has_en:
                return "both"
            if has_ro:
                return "ro"
            if has_en:
                return "en"
        elif field == "group_pref":
            if self._contains_any(lowered, ("explorator", "explorer", "curious", "relaxed", "curios", "relaxat")):
                return "exploratori"
            if self._contains_any(lowered, ("strateg", "competit", "challenge", "provocare")):
                return "strategi"
        elif field == "child_age":
            half = re.search(
                r"\b(\d+)\s+(?:and\s+a\s+half|și\s+(?:o\s+)?jumătate)\b", lowered
            )
            if half:
                val = int(half.group(1)) + 0.5
                if 3 <= val < 18:
                    return str(val)
            m = re.search(r"\b(\d+)\s*(?:ani?|years?\s*old|yo)\b", lowered)
            if m and 3 <= int(m.group(1)) <= 17:
                return m.group(1)
        elif field == "timezone":
            city_tz = self._lookup_city_timezone(lowered)
            if city_tz:
                return city_tz

        return text.strip()

    def _store_intake_answer(self, lead: dict[str, Any], field: str, text: str) -> None:
        lead[field] = self._normalize_intake_answer(field, text)
        lead.setdefault("collected_fields", []).append(field)
        lead["updated_at"] = datetime.now(timezone.utc).isoformat()

    def _maybe_notify_staff(self, phone: str, lead: dict[str, Any]) -> None:
        lang_pref = lead.get("child_language_pref", "")
        lang_display = "English" if lang_pref == "en" else ("Romanian" if lang_pref == "ro" else lang_pref or "-")

        lines = [
            "New lead ready for follow-up 👋",
            f"WhatsApp: {phone}",
            "",
            f"Country: {lead.get('country') or '-'}",
            f"Class language: {lang_display}",
            f"Time zone: {lead.get('timezone') or '-'}",
            f"Child's age: {lead.get('child_age') or '-'}",
            f"Chess experience: {lead.get('prior_experience') or '-'}",
            f"Availability: {lead.get('availability_pref') or '-'}",
            f"Free from: {lead.get('school_dismissal') or '-'}",
            f"Group preference: {lead.get('group_pref') or '-'}",
            f"Extra notes: {lead.get('extra_notes') or '-'}",
        ]

        self.notifier("\n".join(lines))

    _GREETING_WORDS: frozenset[str] = frozenset({
        "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
        "salut", "buna", "bună", "buna ziua", "bună ziua", "servus",
    })

    # Sentences ending with these words are clearly cut off mid-thought.
    _INCOMPLETE_ENDINGS: frozenset[str] = frozenset({
        "i", "to", "for", "the", "a", "an", "and", "or", "but", "in", "at",
        "of", "on", "with", "by", "from", "about", "that", "my", "your", "is",
        "are", "was", "would", "like", "want", "need", "just", "also", "ca",
        "să", "și", "că", "cu", "de", "la", "pe", "un", "o",
    })

    # 2-char words that are legitimate sentence endings and should not be
    # blocked by the short-last-word heuristic.
    _VALID_SHORT_ENDINGS: frozenset[str] = frozenset({
        "ok", "go", "no", "so", "do", "be", "uk", "us", "eu", "ro", "up",
    })

    # Substrings that signal the user is asking about classes / wants to enroll.
    # Only when one of these appears does the greeted stage transition to intake.
    # Deliberately excludes generic info phrases ("tell me", "info", "more about") so
    # parents who want to learn about the school first don't get pushed into intake.
    _ENROLLMENT_SIGNALS: tuple[str, ...] = (
        "sign", "enroll", "register", "class", "lesson", "course",
        "trial", "demo", "interested", "interest", "price", "cost", "fee",
        "schedul", "availab", "slot", "booking", "play", "join",
        "start", "kid", "child", "son", "daughter", "boy", "girl", "age",
        # Romanian
        "înscri", "inscri", "curs", "lecți", "lectie", "șah", "sah",
        "preț", "pret", "interes", "copil", "fiu", "fiica",
    )

    _NON_ANSWERS: frozenset[str] = frozenset({
        "idk", "idc", "idek", "dunno",
        "dont know", "don't know",
        "not sure", "no idea",
        "nu stiu", "nu știu", "habar nu am",
        "hm", "hmm", "huh", "lol",
    })

    # Maps lowercase city names to a human-readable timezone string for Septi.
    # Word-boundary matched, so "la" won't fire on "class" or "language".
    _CITY_TIMEZONES: dict[str, str] = {
        # Canada
        "toronto": "Eastern Time (ET)", "montreal": "Eastern Time (ET)",
        "ottawa": "Eastern Time (ET)", "hamilton": "Eastern Time (ET)",
        "mississauga": "Eastern Time (ET)", "brampton": "Eastern Time (ET)",
        "kitchener": "Eastern Time (ET)", "waterloo": "Eastern Time (ET)",
        "london ontario": "Eastern Time (ET)", "windsor": "Eastern Time (ET)",
        "quebec city": "Eastern Time (ET)", "quebec": "Eastern Time (ET)",
        "vancouver": "Pacific Time (PT)", "victoria": "Pacific Time (PT)",
        "burnaby": "Pacific Time (PT)", "surrey": "Pacific Time (PT)",
        "richmond": "Pacific Time (PT)", "kelowna": "Pacific Time (PT)",
        "calgary": "Mountain Time (MT)", "edmonton": "Mountain Time (MT)",
        "lethbridge": "Mountain Time (MT)", "red deer": "Mountain Time (MT)",
        "winnipeg": "Central Time (CT)", "saskatoon": "Central Time (CT)",
        "regina": "Central Time (CT)",
        "halifax": "Atlantic Time (AT)", "moncton": "Atlantic Time (AT)",
        "fredericton": "Atlantic Time (AT)",
        # USA
        "new york": "Eastern Time (ET)", "nyc": "Eastern Time (ET)",
        "new york city": "Eastern Time (ET)", "miami": "Eastern Time (ET)",
        "boston": "Eastern Time (ET)", "washington dc": "Eastern Time (ET)",
        "atlanta": "Eastern Time (ET)", "philadelphia": "Eastern Time (ET)",
        "pittsburgh": "Eastern Time (ET)", "detroit": "Eastern Time (ET)",
        "cleveland": "Eastern Time (ET)", "charlotte": "Eastern Time (ET)",
        "baltimore": "Eastern Time (ET)", "jacksonville": "Eastern Time (ET)",
        "chicago": "Central Time (CT)", "houston": "Central Time (CT)",
        "dallas": "Central Time (CT)", "austin": "Central Time (CT)",
        "san antonio": "Central Time (CT)", "minneapolis": "Central Time (CT)",
        "nashville": "Central Time (CT)", "memphis": "Central Time (CT)",
        "new orleans": "Central Time (CT)", "kansas city": "Central Time (CT)",
        "st louis": "Central Time (CT)",
        "denver": "Mountain Time (MT)", "phoenix": "Mountain Time (MT)",
        "salt lake city": "Mountain Time (MT)", "albuquerque": "Mountain Time (MT)",
        "los angeles": "Pacific Time (PT)", "san francisco": "Pacific Time (PT)",
        "san jose": "Pacific Time (PT)", "seattle": "Pacific Time (PT)",
        "portland": "Pacific Time (PT)", "las vegas": "Pacific Time (PT)",
        "san diego": "Pacific Time (PT)", "sacramento": "Pacific Time (PT)",
        # Romania
        "bucharest": "Eastern European Time (EET)",
        "cluj": "Eastern European Time (EET)",
        "cluj-napoca": "Eastern European Time (EET)",
        "timisoara": "Eastern European Time (EET)",
        "iasi": "Eastern European Time (EET)",
        "constanta": "Eastern European Time (EET)",
        "brasov": "Eastern European Time (EET)",
        "galati": "Eastern European Time (EET)",
        "craiova": "Eastern European Time (EET)",
        "ploiesti": "Eastern European Time (EET)",
        "oradea": "Eastern European Time (EET)",
        "suceava": "Eastern European Time (EET)",
        "sibiu": "Eastern European Time (EET)",
        "targu mures": "Eastern European Time (EET)",
        # Moldova
        "chisinau": "Eastern European Time (EET)",
        "balti": "Eastern European Time (EET)",
        # UK
        "london": "Greenwich Mean Time (GMT)",
        "birmingham": "Greenwich Mean Time (GMT)",
        "manchester": "Greenwich Mean Time (GMT)",
        "glasgow": "Greenwich Mean Time (GMT)",
        "edinburgh": "Greenwich Mean Time (GMT)",
        "leeds": "Greenwich Mean Time (GMT)",
        "bristol": "Greenwich Mean Time (GMT)",
        "liverpool": "Greenwich Mean Time (GMT)",
        "cardiff": "Greenwich Mean Time (GMT)",
        "belfast": "Greenwich Mean Time (GMT)",
        # Western Europe
        "paris": "Central European Time (CET)",
        "berlin": "Central European Time (CET)",
        "amsterdam": "Central European Time (CET)",
        "brussels": "Central European Time (CET)",
        "madrid": "Central European Time (CET)",
        "barcelona": "Central European Time (CET)",
        "rome": "Central European Time (CET)",
        "milan": "Central European Time (CET)",
        "vienna": "Central European Time (CET)",
        "zurich": "Central European Time (CET)",
        "geneva": "Central European Time (CET)",
        "prague": "Central European Time (CET)",
        "warsaw": "Central European Time (CET)",
        "budapest": "Central European Time (CET)",
        "munich": "Central European Time (CET)",
        "hamburg": "Central European Time (CET)",
        "frankfurt": "Central European Time (CET)",
        "stockholm": "Central European Time (CET)",
        "oslo": "Central European Time (CET)",
        "copenhagen": "Central European Time (CET)",
        "lisbon": "Western European Time (WET)",
        "dublin": "Greenwich Mean Time (GMT)",
        # Eastern Europe
        "helsinki": "Eastern European Time (EET)",
        "athens": "Eastern European Time (EET)",
        "riga": "Eastern European Time (EET)",
        "tallinn": "Eastern European Time (EET)",
        "vilnius": "Eastern European Time (EET)",
        "kyiv": "Eastern European Time (EET)",
        "kiev": "Eastern European Time (EET)",
        # Middle East
        "dubai": "Gulf Standard Time (GST, UTC+4)",
        "abu dhabi": "Gulf Standard Time (GST, UTC+4)",
        "riyadh": "Arabia Standard Time (UTC+3)",
        "tel aviv": "Israel Standard Time (UTC+2)",
        "istanbul": "Turkey Time (TRT, UTC+3)",
        "doha": "Arabia Standard Time (UTC+3)",
        "beirut": "Eastern European Time (EET)",
        "cairo": "Eastern European Time (EET)",
        # Asia
        "tokyo": "Japan Standard Time (JST, UTC+9)",
        "singapore": "Singapore Time (SGT, UTC+8)",
        "hong kong": "Hong Kong Time (HKT, UTC+8)",
        "beijing": "China Standard Time (CST, UTC+8)",
        "shanghai": "China Standard Time (CST, UTC+8)",
        "seoul": "Korea Standard Time (KST, UTC+9)",
        "delhi": "India Standard Time (IST, UTC+5:30)",
        "mumbai": "India Standard Time (IST, UTC+5:30)",
        "bangalore": "India Standard Time (IST, UTC+5:30)",
        "kuala lumpur": "Malaysia Time (MYT, UTC+8)",
        "jakarta": "Western Indonesia Time (WIB, UTC+7)",
        "bangkok": "Indochina Time (ICT, UTC+7)",
        "karachi": "Pakistan Standard Time (PKT, UTC+5)",
        # Oceania
        "sydney": "Australian Eastern Time (AET)",
        "melbourne": "Australian Eastern Time (AET)",
        "brisbane": "Australian Eastern Time (AET)",
        "perth": "Australian Western Time (AWST)",
        "auckland": "New Zealand Standard Time (NZST)",
    }

    def _lookup_city_timezone(self, text: str) -> str | None:
        lowered = text.lower()
        for city, tz in self._CITY_TIMEZONES.items():
            if re.search(r"\b" + re.escape(city) + r"\b", lowered):
                return tz
        return None

    def _is_valid_intake_answer(self, field: str, message: str) -> bool:
        text = message.lower().strip()

        # extra_notes is free-form — any non-empty reply is acceptable
        if field == "extra_notes":
            return True

        if text in self._NON_ANSWERS:
            return False

        if field == "child_age":
            return bool(re.search(r"\d", message))

        if field == "child_language_pref":
            normalized = self._normalize_intake_answer(field, message)
            return normalized in ("ro", "en", "both")

        if field == "group_pref":
            normalized = self._normalize_intake_answer(field, message)
            return normalized in CONSTRAINED_FIELD_VALUES[field]

        return True

    def _handle_lead_intake(self, message: str, phone: str) -> str | list[str] | None:
        if phone in self.bookings:
            return None

        lead = self._get_lead(phone)

        if lead is not None and lead.get("stage") == "faq_only":
            return None

        lang = detect_language(message)

        if lead is None:
            # Very first message — just introduce the assistant. No country question yet.
            lead = self._create_lead(phone, lang, initial_stage="greeted")
            self._save_leads()
            return self._pick(GREETING_INTRO, lang)

        lang = lead.get("lang", "ro")

        if lead.get("stage") == "greeted":
            # If they're still just saying hello, just say hi back — don't push into intake yet.
            if message.lower().strip() in self._GREETING_WORDS:
                return self._pick(GREETING_REPLY, lang)

            # Try rule-based first — handoffs and booking lookups must always go through
            # regardless of enrollment signals. Other rule answers (social media, teachers,
            # etc.) are NOT returned here; the enrollment check below decides what happens
            # next, and if no signal fires, the outer reply() picks them up.
            rule_answer = self._rule_based_reply(message, phone)
            terminal_flat = [
                v
                for pool in (HANDOFF_VARIANTS, BOOKING_NOT_FOUND)
                for variants in pool.values()
                for v in variants
            ]
            if rule_answer and rule_answer in terminal_flat:
                return rule_answer

            # Only transition to intake when the message clearly signals enrollment interest.
            text = message.lower()
            has_signal = any(sig in text for sig in self._ENROLLMENT_SIGNALS)
            if not has_signal:
                # Let the AI (or outer rule) answer naturally; stay in greeted stage.
                return None

            # Clear enrollment intent — ask country to kick off intake.
            lead["stage"] = "intake_in_progress"
            self._save_leads()
            return self._pick(INTAKE_TRANSITION, lang)

        # stage == "intake_in_progress"

        # Greeting mid-intake — acknowledge warmly and re-ask the pending question in
        # the same message so it doesn't feel like a cold ignored hello.
        if message.lower().strip() in self._GREETING_WORDS:
            pending_field = self._next_missing_field(lead)
            if pending_field:
                q = INTAKE_QUESTIONS[pending_field][lang]
                opener = random.choice(
                    ["Hey! 🙂 ", "Hi! 🙂 ", "Hey there! "] if lang == "en"
                    else ["Bună! 🙂 ", "Salut! 🙂 ", "Hey! 🙂 "]
                )
                return f"{opener}{q}"
            return None

        pending_field = self._next_missing_field(lead)

        if pending_field is None:
            return None

        # extra_notes accepts any reply — don't let rule-based handlers steal it.
        # (e.g. "Thanks, nothing else" would otherwise trigger the thanks handler.)
        if pending_field != "extra_notes" and (
            self._rule_based_reply(message, phone) or self._mentions_ai_topic(message)
        ):
            return None

        # Reject answers that don't make sense for the question being asked.
        # Bare digits count as length-1 so skip the length check for child_age;
        # all other fields need at least 2 alphanumeric characters.
        alphanum = re.sub(r"[^a-zA-Z0-9]", "", message)
        too_short = pending_field != "child_age" and len(alphanum) < 2
        if too_short or not self._is_valid_intake_answer(pending_field, message):
            opener = random.choice(
                ["Hmm, didn't quite catch that 😊 ", "Not sure I got that, ", "Sorry, didn't get that. "]
                if lang == "en" else
                ["Hmm, nu am înțeles 😊 ", "Nu am prins bine, ", "Scuze, nu am înțeles. "]
            )
            return f"{opener}{INTAKE_QUESTIONS[pending_field][lang]}"

        # If the child speaks both languages, ask which they'd prefer for class.
        if pending_field == "child_language_pref":
            if self._normalize_intake_answer("child_language_pref", message) == "both":
                if lang == "en":
                    return ["Nice, they're bilingual 🙂", "Which language would your child prefer to speak during chess classes?"]
                else:
                    return ["Super, sunt bilingvi 🙂", "Ce limbă ar prefera copilul să vorbească la orele de șah?"]

        # Sep7Ro classes are for children under 18 only.
        if pending_field == "child_age":
            age_match = re.search(r"\b(\d+)\b", message)
            if age_match and int(age_match.group(1)) >= 18:
                if lang == "en":
                    return (
                        "Our chess classes are designed for children under 18 🙂 "
                        "If you have a younger child you'd like to enroll, how old are they?"
                    )
                else:
                    return (
                        "Clasele noastre de șah sunt pentru copii sub 18 ani 🙂 "
                        "Dacă aveți un copil mai mic pe care doriți să îl înregistrați, câți ani are?"
                    )

        self._store_intake_answer(lead, pending_field, message)

        # If the parent just told us their country, override the phone-based currency bucket.
        if pending_field == "country":
            new_bucket = self._infer_currency_from_country(lead["country"] or message)
            if new_bucket:
                lead["currency_bucket"] = new_bucket

        # Multi-field: scan ALL remaining fields for extractable signals,
        # skipping ones we can't infer (e.g. prior_experience) and continuing
        # to the ones after them. This lets "He's 8, weekends, Exploratori"
        # capture age + availability + group even though prior_experience sits
        # in between and still needs a direct answer.
        for field in REQUIRED_INTAKE_FIELDS:
            if field in lead.get("collected_fields", []):
                continue
            extracted = self._try_extract_field(field, message)
            if extracted is not None:
                self._store_intake_answer(lead, field, extracted)

        next_field = self._next_missing_field(lead)

        if next_field is not None:
            self._save_leads()
            return [self._pick(INTAKE_ACK, lang), INTAKE_QUESTIONS[next_field][lang]]

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

    def _social_media_reply(self, lang: str) -> str:
        sm = self.company_data.get("social_media", {})
        instagram = sm.get("instagram", "")
        tiktok = sm.get("tiktok", "")
        facebook = sm.get("facebook", "")
        youtube = sm.get("youtube", "")
        linktree = sm.get("linktree", "")

        if lang == "ro":
            return (
                f"Ne găsești pe toate platformele 🙂\n\n"
                f"Instagram: {instagram}\n"
                f"TikTok: {tiktok}\n"
                f"Facebook: {facebook}\n"
                f"YouTube: {youtube}\n\n"
                f"Sau vezi tot pe linkul ăsta: {linktree}"
            )
        return (
            f"You can find us on all platforms 🙂\n\n"
            f"Instagram: {instagram}\n"
            f"TikTok: {tiktok}\n"
            f"Facebook: {facebook}\n"
            f"YouTube: {youtube}\n\n"
            f"Or see everything in one place: {linktree}"
        )

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

        if self._contains_any(
            text,
            (
                "instagram", "tiktok", "facebook", "youtube",
                "social media", "social", "linktree",
                "retele sociale", "rețele sociale",
                "pagina de facebook", "pagina de instagram",
            ),
        ):
            return self._social_media_reply(lang)

        if self._contains_any(
            text,
            (
                "google review", "google rating", "reviews", "recenzii", "recenzi",
                "what do people say", "what do parents say", "testimonial",
            ),
        ):
            reviews_url = self.company_data.get("trust_links", {}).get("google_reviews", "")
            if reviews_url:
                if lang == "ro":
                    return f"Iată recenziile părinților pe Google 🙂 {reviews_url}"
                return f"Here are the Google reviews from other parents 🙂 {reviews_url}"
            return self._handoff(lang)

        if self._contains_any(
            text,
            (
                "free guide", "chess guide", "free resource", "pdf", "download",
                "ghid gratuit", "ghid de sah", "ghid de șah", "resurse gratuite",
            ),
        ):
            fr = self.company_data.get("free_resources", {})
            url = fr.get("chess_guide_url", "")
            desc = self._bilingual(fr.get("chess_guide_description", {}), lang) or ""
            if url:
                if lang == "ro":
                    return f"Avem un ghid gratuit de șah 🙂 {desc}\n\n{url}"
                return f"We have a free chess guide 🙂 {desc}\n\n{url}"
            return self._handoff(lang)

        if self._contains_any(
            text,
            (
                "teacher", "instructor", "coach", "who teaches",
                "who is septi", "about septi", "about the teacher",
                "profesor", "cine preda", "cine sunt profesorii",
                "cine e septi", "despre septi",
            ),
        ):
            raw_instructors = self.company_data.get("instructors", {})
            instructor_list = raw_instructors.get(lang) or raw_instructors.get("en") or []
            if instructor_list:
                body = "\n\n".join(instructor_list)
                if lang == "ro":
                    return f"Iată cine predă la Sep7Ro 🙂\n\n{body}"
                return f"Here's who teaches at Sep7Ro 🙂\n\n{body}"
            return self._handoff(lang)

        if self._contains_any(
            text,
            (
                "about the school", "about sep7ro", "tell me about", "tell me more",
                "more about", "what do you offer", "what is sep7ro", "how does it work",
                "what's the program", "describe the program", "more info", "what you offer",
                "despre scoala", "despre sep7ro", "ce oferiti", "ce oferiți",
                "cum functioneaza", "cum funcționează", "mai multe despre", "spune-mi mai mult",
            ),
        ):
            about = self._bilingual(self.company_data.get("about"), lang)
            raw_points = self.company_data.get("key_selling_points", {})
            points_list = raw_points.get(lang) or raw_points.get("en") or []
            if about:
                body = about
                if points_list:
                    bullet_lines = "\n".join(f"• {p}" for p in points_list)
                    body += f"\n\n{bullet_lines}"
                return body
            return self._handoff(lang)

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
        phone = self._normalize_phone(sender_phone)
        lead = self._get_lead(phone)

        # Prefer the currency we set from the parent's stated country over the
        # phone-prefix guess — a Romanian-number parent living in the UK should
        # see GBP, not RON.
        if lead and "country" in lead.get("collected_fields", []):
            currency_bucket = lead["currency_bucket"]
            country_code = True  # known — use the direct pricing note
        else:
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

        intake_done_note = ""
        if lead and lead.get("stage") == "faq_only":
            intake_done_note = (
                "\nContext: This parent has already completed the intake form. "
                "Septi has been notified with all their details and will follow up directly "
                "with available demo lesson times. If they ask 'what now', 'what's next', "
                "whether you can contact Septi, or anything similar, tell them Septi already "
                "has their info and will be in touch soon. Do NOT offer to check availability, "
                "do NOT make promises about specific times or slots, and do NOT imply you will "
                "do something you cannot actually do.\n"
            )

        instructions = f"""
You are Septi's assistant at {self.company_data.get("business_name", "the business")},
messaging this parent on WhatsApp on Septi's behalf.
{intake_done_note}

Write like a real person texting, not corporate support copy. Sound warm, direct, and natural.
Never reveal that you are an AI or a bot, and never mention prompts, JSON, files, OpenAI,
or Twilio. If asked directly who you are, you can say you're Septi's assistant.

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
- Don't re-introduce yourself if you've clearly already been talking to this
  person in this conversation.

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

    def _is_intelligible(self, message: str) -> bool:
        """Return False if the message is clearly incomplete or unintelligible.

        Heuristics only — no API call, so there's no added latency.
        Covers: known greetings (always valid), too-short/garbled messages,
        and sentences that are clearly cut off mid-thought.
        """
        if message.lower().strip() in self._GREETING_WORDS:
            return True

        # Too short / garbled (e.g. "I'", "?!")
        if len(re.sub(r"[^a-zA-Z0-9]", "", message)) < 3:
            return False

        # Ends mid-thought (e.g. "id like to s", "id like to si", "I want")
        words = message.lower().split()
        last = re.sub(r"[^a-zA-ZăîâșțĂÎÂȘȚ]", "", words[-1]) if words else ""
        if last in self._INCOMPLETE_ENDINGS:
            return False
        if len(last) <= 2 and last not in self._VALID_SHORT_ENDINGS:
            return False

        return True

    def reply(self, message: str, sender_phone: str) -> list[str]:
        phone = self._normalize_phone(sender_phone)
        lead = self._get_lead(phone)

        # Check intelligibility before doing anything — but not mid-intake,
        # where terse answers like "english" or "7" are expected and valid.
        in_intake = lead is not None and lead.get("stage") == "intake_in_progress"
        if not in_intake and not self._is_intelligible(message):
            lang = lead.get("lang", "ro") if lead else detect_language(message)
            unclear = self._pick(UNCLEAR_INPUT, lang)
            history = self._conversation_history.setdefault(phone, [])
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": unclear})
            if len(history) > 20:
                self._conversation_history[phone] = history[-20:]
            self._save_history()
            return [unclear]

        intake_reply = self._handle_lead_intake(message, phone)
        if intake_reply is not None:
            parts = intake_reply if isinstance(intake_reply, list) else [intake_reply]
        else:
            rule_reply = self._rule_based_reply(message, sender_phone)
            if rule_reply:
                reply_text = rule_reply
            elif self.ai_enabled:
                reply_text = self._ai_reply(message, sender_phone)
            else:
                reply_text = self._handoff(detect_language(message))

            # Re-prompt: if this phone has an intake still in progress, append
            # the current question so the parent knows where we left off.
            lead = self._get_lead(phone)
            if lead and lead.get("stage") == "intake_in_progress":
                pending = self._next_missing_field(lead)
                if pending:
                    lang = lead.get("lang", "ro")
                    reply_text = f"{reply_text}\n\n{INTAKE_QUESTIONS[pending][lang]}"

            parts = [reply_text]

        history_text = "\n\n".join(parts)
        history = self._conversation_history.setdefault(phone, [])
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": history_text})
        if len(history) > 20:
            self._conversation_history[phone] = history[-20:]
        self._save_history()

        return parts