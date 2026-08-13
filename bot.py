from __future__ import annotations

import json
import os
import random
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable
from notifications import send_staff_notification, send_whatsapp_message
import database as db

# In production set DATA_DIR to a persistent volume path (e.g. /data on Render).
# Falls back to the project directory for local development.
_data_dir_env = os.getenv("DATA_DIR", "").strip()
BASE_DIR = Path(_data_dir_env) if _data_dir_env else Path(__file__).resolve().parent

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

INTAKE_QUESTIONS: dict[str, dict[str, str]] = {
    "parent_name": {
        "en": "What's your name?",
        "ro": "Cum te numești?",
    },
    "child_name": {
        "en": "And what's your child's name?",
        "ro": "Și cum îl cheamă pe copil?",
    },
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
    "referral_source": {
        "en": "Almost done! How did you hear about Sep7Ro?",
        "ro": "Aproape gata! Cum ai aflat de Sep7Ro?",
    },
    "demo_interest": {
        "en": "Last one 🙂 Would your child be up for a free 50-minute demo lesson to try it out?",
        "ro": "Ultima întrebare 🙂 Ar vrea copilul să încerce o lecție demo gratuită de 50 de minute?",
    },
}

GREETING_INTRO: dict[str, list[str]] = {
    "en": [
        "Hey! I'm Septi's assistant at Sep7Ro 🙂 How can I help you?",
        "Hi there! I'm the assistant here at Sep7Ro, how can I help?",
        "Hey, I'm Septi's assistant from Sep7Ro! What can I do for you?",
    ],
    "ro": [
        "Bună! Sunt asistentul lui Septi la Sep7Ro 🙂 Cu ce te pot ajuta?",
        "Salut! Sunt asistentul de la Sep7Ro, cu ce te ajut?",
        "Hey, sunt asistentul lui Septi de la Sep7Ro! Cu ce pot ajuta?",
    ],
}

CLOSING_MESSAGE: dict[str, list[str]] = {
    "en": [
        "Perfect, got everything! 🙂 Septi will reach out within 24 hours to schedule your free demo lesson",
        "Awesome, thank you! Septi will get back to you within 24 hours to set up the free demo",
        "Got it, thanks! 👍 Septi will be in touch within 24 hours with some times for the demo lesson",
    ],
    "ro": [
        "Perfect, am notat tot! 🙂 Septi te va contacta în 24 de ore pentru a programa lectia demo gratuită",
        "Super, mulțumesc! Septi revine în 24 de ore cu variante pentru lectia demo",
        "Am notat, mersi! 👍 Septi te contactează în 24 de ore cu orele disponibile pentru demo",
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
        "Happy to help! What's your name?",
        "Of course! Just a couple of quick questions — what's your name?",
        "Sure thing! What's your name?",
    ],
    "ro": [
        "Cu plăcere! Cum te numești?",
        "Sigur! Câteva întrebări rapide — cum te numești?",
        "Clar! Cum te numești?",
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

THINKING_IT_OVER: dict[str, list[str]] = {
    "en": [
        "Of course, take your time 🙂 I'm here if any questions come up",
        "Absolutely, no rush at all! Reach out whenever you're ready",
        "Sure thing 🙂 Feel free to come back with any questions",
        "Of course! And if anything comes to mind, just ask 🙂",
    ],
    "ro": [
        "Bineînțeles, ia-ți timp 🙂 Sunt aici dacă apar întrebări",
        "Absolut, nicio grabă! Revino oricând ești gata",
        "Sigur 🙂 Nu ezita să revii cu orice întrebări",
        "Desigur! Și dacă îți vine ceva în minte, întreabă 🙂",
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
        "That one's best answered by Septi directly 🙂 feel free to ask him when he reaches out",
        "Good question — Septi will have the full answer on that, I'd bring it up with him",
        "That's a bit outside what I can confirm right now, Septi's the one to ask 👍",
        "I don't have that detail handy — Septi can answer that when he contacts you",
        "Best to run that by Septi directly, he'll know exactly 🙂",
    ],
    "ro": [
        "Asta e mai bine să îl întrebi direct pe Septi 🙂 poți să-l întrebi când te contactează",
        "Bună întrebare — Septi va ști exact răspunsul, ridic-o cu el",
        "Nu pot confirma asta acum, Septi e cel mai bun să răspundă 👍",
        "Nu am detaliul acesta la îndemână — Septi îți poate răspunde când te contactează",
        "Cel mai bine să-l întrebi direct pe Septi, el știe exact 🙂",
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

CURRENCY_DEFAULT_NOTE = {
    "en": "I'll quote prices in EUR, let me know if you'd like a different currency",
    "ro": "Voi da prețurile în EUR, spune-mi dacă preferi altă moneda",
}

PRICING_NEEDS_COUNTRY: dict[str, list[str]] = {
    "en": [
        "What country are you based in? Just want to make sure I give you the right prices 🙂",
        "Happy to share pricing! What country are you in so I can give you the right numbers?",
        "Sure! Which country are you in? Prices vary a bit so I want to give you the accurate ones 🙂",
    ],
    "ro": [
        "Din ce țară ești? Vreau să îți dau prețurile corecte 🙂",
        "Cu plăcere! Din ce țară ești ca să îți dau cifrele corecte?",
        "Sigur! Din ce țară ești? Prețurile diferă un pic, vreau să îți dau varianta corectă 🙂",
    ],
}

POST_INTAKE_NUDGE: dict[str, list[str]] = {
    "en": [
        "Hey! Just wanted to check in 🙂 Did Septi manage to reach you about the demo lesson? Let me know if you have any questions in the meantime",
        "Hi! Wanted to follow up on your sign-up. If you haven't heard from Septi yet, he'll be in touch very soon. Any questions while you wait?",
        "Hey, just checking in 🙂 Everything's in with Septi. Do you have any questions about the demo or the program before he reaches out?",
    ],
    "ro": [
        "Bună! Voiam să verific 🙂 A reușit Septi să te contacteze despre lectia demo? Spune-mi dacă ai întrebări între timp",
        "Salut! Voiam să dau un semn după înregistrare. Dacă nu ai primit vești de la Septi, o să te contacteze foarte curând. Ai întrebări?",
        "Bună, o scurtă verificare 🙂 Totul e la Septi. Ai întrebări despre demo sau program înainte să te contacteze?",
    ],
}

ABANDONED_INTAKE_NUDGE: dict[str, list[str]] = {
    "en": [
        "Hey, just checking in 🙂 You were halfway through signing up for a demo lesson at Sep7Ro. Still interested? Happy to pick up where you left off",
        "Hi! You started the sign-up a little while back but didn't quite finish. No rush at all, just wanted to make sure you hadn't lost the thread",
        "Hey there! You were mid-way through the Sep7Ro sign-up. Still want to book a free demo for your child? We can continue whenever you're ready 🙂",
    ],
    "ro": [
        "Bună, voiam să verific 🙂 Ai început formularul pentru lectia demo la Sep7Ro. Mai ești interesat/ă? Putem continua oricând",
        "Salut! Ai început înregistrarea acum ceva timp dar nu ai terminat. Nică grabă, voiam doar să mă asigur că nu ai pierdut firul",
        "Bună! Erai la jumătatea formularului de înscriere Sep7Ro. Vrei să programezi o lectie demo gratuită pentru copilul tău? Putem continua oricând 🙂",
    ],
}

THINKING_IT_OVER_NUDGE: dict[str, list[str]] = {
    "en": [
        "Hey! Just checking in 🙂 Did you get a chance to think it over? Happy to answer any questions if that helps",
        "Hi, just wanted to follow up 🙂 Have you had a chance to think about the chess program? No rush at all, just here if you need anything",
        "Hey, hope everything's going well 🙂 Just wanted to see if you'd had a chance to think about it and if there's anything I can help with",
    ],
    "ro": [
        "Bună! Voiam să verific 🙂 Ai reușit să te gândești? Sunt aici dacă ai întrebări",
        "Salut, voiam să dau un semn 🙂 Ai mai avut ocazia să te gândești la program? Nicio grabă, spune-mi dacă pot ajuta",
        "Bună, sper că ești bine 🙂 Voiam să văd dacă ai avut ocazia să te gândești și dacă pot ajuta cu ceva",
    ],
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
    # Information questions mid-intake
    "price", "cost", "pret", "preț", "cat costa", "câtă costă", "discount", "reducere",
    "lichess", "online account", "cont online",
    "tournament", "turneu",
    "review", "recenzi", "benefits", "beneficii", "teachers", "profesori",
    # Conversational replies that clearly aren't answers to a pending intake field
    "think about it", "i'll think", "let me think",
    "sounds good", "sounds great", "sounds cool", "sounds amazing",
    "sounds nice", "sounds interesting", "pretty cool",
    "maybe later", "not ready", "not sure yet",
    "will let you know", "i'll let you know",
    "are you back", "you back", "still there", "you there",
    "hello again", "hi again", "hey again",
    "o să mă gândesc", "mă gândesc", "suna bine", "sună bine",
    "ești acolo", "ești înapoi",
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
    language's whole-word markers appear more often. On a tie, short or simple
    messages (under 15 characters or fewer than 3 words) default to English to
    avoid misclassifying casual English phrases like 'ok', 'cool', 'sounds good',
    or 'thats cool' as Romanian. Longer ambiguous messages keep Romanian as the
    default (primary audience)."""
    lowered = text.lower()

    if any(char in lowered for char in "ăâîșț"):
        return "ro"

    ro_hits = sum(1 for marker in RO_WORD_MARKERS if re.search(rf"\b{marker}\b", lowered))
    en_hits = sum(1 for marker in EN_WORD_MARKERS if re.search(rf"\b{marker}\b", lowered))

    if en_hits > ro_hits:
        return "en"
    if ro_hits > en_hits:
        return "ro"

    # 0 vs 0 tie — no markers at all → always English (Romanian text will
    # always have at least one Romanian word or diacritic).
    if ro_hits == 0 and en_hits == 0:
        return "en"

    # Tied non-zero: short messages lean English, longer ones lean Romanian.
    words = lowered.split()
    if len(lowered.strip()) <= 20 or len(words) <= 4:
        return "en"

    return "ro"


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
        self.enrollments_path = BASE_DIR / "enrollments.json"
        self.enrollments: dict[str, list[dict[str, Any]]] = self._load_leads(self.enrollments_path)
        self.schedule: list[dict[str, Any]] = self._load_schedule()
        self.notifier = notifier or send_staff_notification
        self._last_pick: dict[Any, str] = {}
        self._leads_lock = Lock()
        self._conversation_history: dict[str, list[dict[str, str]]] = {}

        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o").strip()
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

    def clear_state(self) -> None:
        """Wipe all leads, enrollments, and conversation history from memory and disk."""
        with self._leads_lock:
            self.leads = {}
            self._conversation_history = {}
            self.enrollments = {}
            if self._db_available:
                db.delete_all_leads()
                db.delete_all_history()
            self._save_leads()
            self._save_enrollments()

    def clear_lead(self, phone: str) -> bool:
        """Remove one phone's lead and conversation history. Returns True if the lead existed."""
        phone = self._normalize_phone(phone)
        with self._leads_lock:
            existed = phone in self.leads
            self.leads.pop(phone, None)
            self._conversation_history.pop(phone, None)
            if self._db_available:
                db.delete_lead(phone)
                db.delete_history(phone)
            self._save_leads()
        return existed

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

            # Ensure last_seen is timezone-aware for comparison
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)

            if last_seen >= cutoff:
                continue

            lang = lead.get("lang", "en")

            message = self._pick(ABANDONED_INTAKE_NUDGE, lang)
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

            message = self._pick(POST_INTAKE_NUDGE, lang)
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
            message = self._pick(THINKING_IT_OVER_NUDGE, lang)
            if send_whatsapp_message(f"whatsapp:{phone}", message):
                with self._leads_lock:
                    lead["thinking_it_over_nudge_sent"] = True
                    self._save_leads()

    def _save_leads(self) -> None:
        # Must be called while _leads_lock is held (directly or via _reply_locked).
        if self._db_available:
            db.save_all_leads(self.leads)
        # Always keep JSON in sync as a local backup.
        with self.leads_path.open("w", encoding="utf-8") as file:
            json.dump(self.leads, file, ensure_ascii=False, indent=2)

    def _append_to_history(self, phone: str, user_msg: str, assistant_msg: str) -> None:
        history = self._conversation_history.setdefault(phone, [])
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": assistant_msg})
        if len(history) > 20:
            self._conversation_history[phone] = history[-20:]
            history = self._conversation_history[phone]
        if self._db_available:
            db.save_history(phone, history)

    def _is_returning_lead(self, lead: dict) -> bool:
        """True if the lead's last activity was more than 2 hours ago."""
        last_seen = lead.get("updated_at") or lead.get("created_at")
        if not last_seen:
            return False
        try:
            last_dt = datetime.fromisoformat(last_seen)
            return (datetime.now(timezone.utc) - last_dt) > timedelta(hours=2)
        except Exception:
            return False

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

        if field == "school_dismissal":
            # If the parent already mentioned a start time ("after 3:30 PM",
            # "from 4pm", "at 3:30 PM") when answering availability, there's
            # no need to ask again — extract it directly.
            lowered = message.lower()
            # "after/from/around/at/starting X:XX am/pm" or "X:XX am/pm"
            m = re.search(
                r"\b(?:after|from|around|at|starting|începând\s+de\s+la|după|de\s+la)\s+"
                r"(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b",
                lowered,
                re.IGNORECASE,
            )
            if not m:
                # bare "3:30 PM" or "16:00" (24h)
                m = re.search(r"\b(\d{1,2}:\d{2}\s*(?:am|pm)?)\b", lowered, re.IGNORECASE)
            if m:
                hour_str = re.search(r"\d{1,2}", m.group(0))
                # 1–22 covers both 12-hour (1pm = "1") and 24-hour (16:00)
                if hour_str and 1 <= int(hour_str.group()) <= 22:
                    return m.group(0).strip()

        return None

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

    def _is_human_request(self, message: str) -> bool:
        """Returns True if the message clearly asks to speak to a human / Septi."""
        return self._contains_any(message.lower(), self._HUMAN_REQUEST_SIGNALS)

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
            has_other = self._contains_any(lowered, (
                "another", "something else", "other language", "and another",
                "also", "plus", "și altceva", "si altceva", "alta limba", "altă limbă",
            ))
            if has_ro and has_en:
                return "both"
            if self._contains_any(lowered, (
                "both", "amandoua", "amândouă", "ambele",
                "si una si alta", "și una și alta",
                "si romana si", "și română și",
            )):
                return "both"
            # "english and something else" / "english and another" → treat as both
            if has_en and has_other:
                return "both"
            if has_ro and has_other:
                return "both"
            if has_ro:
                return "ro"
            if has_en:
                return "en"
        elif field == "group_pref":
            if self._contains_any(lowered, ("explorator", "explorer", "curious", "relaxed", "curios", "relaxat")):
                return "exploratori"
            if self._contains_any(lowered, ("strat", "competit", "challenge", "provocare")):
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
        elif field in ("parent_name", "child_name"):
            return text.strip().title()
        elif field == "demo_interest":
            yes_words = (
                "yes", "yeah", "yep", "yup", "sure", "absolutely", "definitely",
                "of course", "sounds good", "why not", "love to", "would love",
                "da", "sigur", "desigur", "bineinteles", "bineînțeles",
                "cu siguranta", "cu siguranță", "vreau", "vrem",
            )
            no_words = (
                "no", "nope", "not interested", "not now", "not yet",
                "maybe later", "maybe another time", "skip", "pass",
                "nu", "nu vreau", "nu acum", "poate mai tarziu", "poate mai târziu",
            )
            if any(w in lowered for w in yes_words):
                return "yes"
            if any(w in lowered for w in no_words):
                return "no"

        return text.strip()

    def _store_intake_answer(self, lead: dict[str, Any], field: str, text: str) -> None:
        lead[field] = self._normalize_intake_answer(field, text)
        lead.setdefault("collected_fields", []).append(field)
        lead["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Flag if the parent mentions more than one child so Septi knows upfront.
        if field == "child_age":
            lowered = text.lower()
            multiple_ages = len(re.findall(r"\b\d+\b", text)) > 1
            multi_words = any(w in lowered for w in ("and", " & ", "both", "two kids", "two children", "2 kids", "2 children", "doi copii", "ambii"))
            if multiple_ages or multi_words:
                lead["multi_child"] = True

    # Phrases that mean "nothing notable" for free-form fields like extra_notes.
    _NOTIFICATION_NEGATIVES: frozenset[str] = frozenset({
        "no", "nope", "nah", "none", "nothing", "n/a", "na", "not really",
        "not right now", "not at the moment", "no thanks", "no thank you",
        "nothing special", "nothing in particular", "nothing for now",
        "no notes", "no extra notes", "no additional notes",
        "nothing else", "nothing to add", "no questions", "no concerns",
        "nu", "nu prea", "nimic", "nimic special", "nimic deocamdata",
    })

    def _clean_for_notification(self, field: str, raw: str | None) -> str:
        """Return a short, clean version of a raw intake answer for Septi's notification."""
        if not raw:
            return "-"
        text = raw.strip()
        lower = text.lower()

        # Free-form fields: if the answer is essentially "no/nothing", show a dash.
        if field in ("extra_notes", "referral_source"):
            if lower in self._NOTIFICATION_NEGATIVES or lower.startswith(("not really", "no ", "nothing", "nope", "nah")):
                return "-"
            # Truncate very long answers
            return text[:80] + ("..." if len(text) > 80 else "")

        if field in ("parent_name", "child_name"):
            # Strip common "my name is / his name is / I'm …" prefixes.
            for prefix in (
                "my name is ", "my name's ", "i'm ", "i am ", "it's ", "its ",
                "his name is ", "her name is ", "their name is ",
                "the child's name is ", "child's name is ", "name is ",
            ):
                if lower.startswith(prefix):
                    text = text[len(prefix):]
                    lower = text.lower()
                    break
            return text.strip().title()

        if field == "country":
            # "Canada, Toronto specifically" → "Canada"
            text = re.split(r",", text)[0].strip()
            text = re.sub(
                r"\s+(?:specifically|particularly|mainly|mostly|especially)\s*$",
                "", text, flags=re.IGNORECASE,
            )
            return text.strip()

        if field == "school_dismissal":
            # Extract the time expression, drop surrounding filler.
            # "Anytime after 3:30 is great" → "after 3:30"
            # "free from 4pm" → "from 4pm"
            m = re.search(
                r"\b(?:after|from|around|at|starting)\s+\d{1,2}(?::\d{2})?(?:\s*(?:am|pm))?\b",
                lower, re.IGNORECASE,
            )
            if not m:
                # Bare "3:30 PM" or "16:00" with optional am/pm
                m = re.search(r"\b\d{1,2}:\d{2}(?:\s*(?:am|pm))?\b", lower, re.IGNORECASE)
            return m.group(0).strip() if m else text

        if field == "availability_pref":
            # "Weekdays, specifically Tuesdays after 3:30 PM" → "Tuesdays after 3:30 PM"
            cleaned = re.sub(
                r"\b(?:specifically|usually|generally|mainly|mostly|particularly)\b\s*",
                "", text, flags=re.IGNORECASE,
            )
            # Drop a leading generic day-category if a specific day follows
            cleaned = re.sub(
                r"^(?:weekdays|weekends|any day|anytime)[,.]?\s*",
                "", cleaned, flags=re.IGNORECASE,
            ).strip().rstrip(",").strip()
            return cleaned if cleaned else text

        if field == "prior_experience":
            # Map verbose answers to a clean label when possible.
            kw_map = [
                (("no experience", "never played", "never tried", "complete beginner",
                  "hasn't played", "has not played", "nu a jucat", "fara experienta",
                  "fără experiență", "deloc"), "No experience"),
                (("beginner", "just started", "a bit", "little bit", "very basic",
                  "not much", "basic", "incepator", "începător"), "Beginner"),
                (("intermediate", "some experience", "decent", "played for",
                  "intermediate", "mediu"), "Intermediate"),
                (("advanced", "competitive", "tournaments", "avansat"), "Advanced"),
            ]
            for keywords, label in kw_map:
                if any(kw in lower for kw in keywords):
                    return label
            return text

        if field == "group_pref":
            return text.title()

        return text

    def _maybe_notify_staff(self, phone: str, lead: dict[str, Any]) -> None:
        c = self._clean_for_notification  # shorthand
        lang_pref = lead.get("child_language_pref", "")
        lang_display = "English" if lang_pref == "en" else ("Romanian" if lang_pref == "ro" else lang_pref or "-")

        multi_child_note = " (multiple children — confirm details)" if lead.get("multi_child") else ""
        wa_link = f"https://wa.me/{phone.lstrip('+')}"

        lines = [
            "New lead ready for follow-up 👋",
            f"WhatsApp: {phone} | {wa_link}",
            f"Parent: {c('parent_name', lead.get('parent_name'))}",
            f"Child: {c('child_name', lead.get('child_name'))}",
            "",
            f"Country: {c('country', lead.get('country'))}",
            f"Class language: {lang_display}",
            f"Time zone: {lead.get('timezone') or '-'}",
            f"Child's age: {lead.get('child_age') or '-'}{multi_child_note}",
            f"Chess experience: {c('prior_experience', lead.get('prior_experience'))}",
            f"Availability: {c('availability_pref', lead.get('availability_pref'))}",
            f"Free from: {c('school_dismissal', lead.get('school_dismissal'))}",
            f"Group preference: {c('group_pref', lead.get('group_pref'))}",
            f"Extra notes: {c('extra_notes', lead.get('extra_notes'))}",
            f"Heard about us via: {c('referral_source', lead.get('referral_source'))}",
        ]

        self.notifier("\n".join(lines))

    def _notify_human_request(self, phone: str, lead: dict[str, Any]) -> None:
        """Send Septi a direct-contact alert when a user asks to speak to a human."""
        wa_link = f"https://wa.me/{phone.lstrip('+')}"
        parent = lead.get("parent_name") or "-"
        lines = [
            "🙋 Someone wants to speak with you directly",
            f"WhatsApp: {phone} | {wa_link}",
            f"Parent: {parent}",
            f"Child: {lead.get('child_name') or '-'}",
        ]
        body = "\n".join(lines)
        print(f"[NOTIFY] Firing human-request alert for {phone}")
        result = self.notifier(body)
        print(f"[NOTIFY] Alert sent={result}")

    _THINKING_IT_OVER_PHRASES: tuple[str, ...] = (
        "think about it", "i'll think", "let me think", "need some time",
        "take some time", "not sure yet", "maybe later", "i'll consider",
        "i'll let you know", "will let you know", "not ready",
        "mă gândesc", "ma gandesc", "o să mă gândesc", "o sa ma gandesc",
        "nu sunt sigur", "poate mai târziu", "poate mai tarziu",
    )

    _GREETING_WORDS: frozenset[str] = frozenset({
        "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
        "salut", "buna", "bună", "buna ziua", "bună ziua", "servus",
    })

    # Phrases that mean the parent no longer wants to proceed with enrollment.
    # When detected mid-intake, stage is reset to "greeted" and AI responds warmly.
    _PRICING_QUESTION_HINTS: tuple[str, ...] = (
        "how much", "what does it cost", "what's the cost", "what is the cost",
        "how much is it", "how much are", "what are the prices", "what are the fees",
        "pricing", "price?", "prices?", "cost?", "fee?", "fees?",
        "cât costă", "cat costa", "cât e prețul", "cat e pretul", "cât sunt", "cat sunt",
        "preț", "pret", "tarif", "tarife",
    )

    _OPT_OUT_PHRASES: tuple[str, ...] = (
        "changed my mind", "change my mind",
        "not interested", "not interested anymore",
        "never mind", "nevermind", "nvm",
        "forget it", "forget about it",
        "i don't want to", "i dont want to",
        "actually no", "not anymore",
        "i'll pass", "ill pass",
        "not right now", "maybe another time",
        "actually forget",
        # Romanian
        "m-am răzgândit", "m-am razgandit",
        "nu mai vreau", "nu mai sunt interesat",
        "nu mai sunt interesată", "lasa balta", "lasă baltă",
        "renunț", "renunt",
    )

    # Phrases that signal the parent wants to speak to a human / Septi directly.
    # Checked before intake processing so mid-intake requests are always caught.
    _HUMAN_REQUEST_SIGNALS: tuple[str, ...] = (
        # English — explicit human/person requests
        "speak to a human", "talk to a human", "speak to someone", "talk to someone",
        "speak to a person", "talk to a person", "speak to a real person",
        "talk to a real person", "want a human", "need a human",
        "speak to an agent", "talk to an agent", "human agent", "human support",
        "speak to the owner", "talk to the owner", "speak to the manager",
        "talk to the manager", "speak to staff", "talk to staff",
        "speak to septi", "talk to septi", "contact septi", "reach septi",
        "connect me to", "put me through to", "i want to talk to",
        "i want to speak to", "can i speak to", "can i talk to",
        "get me a human", "let me talk to", "let me speak to",
        "transfer me", "escalate", "real support",
        # English — complaints / refunds / urgent
        "complaint", "complain", "refund", "emergency", "urgent help",
        "manager", "supervisor", "human", "real person", "staff",
        # Romanian — speak to a human / Septi
        "vreau să vorbesc cu", "vreau sa vorbesc cu",
        "doresc să vorbesc cu", "doresc sa vorbesc cu",
        "pot să vorbesc cu", "pot sa vorbesc cu",
        "pot vorbi cu", "aș vrea să vorbesc cu", "as vrea sa vorbesc cu",
        "vreau să vorbesc cu cineva", "vreau sa vorbesc cu cineva",
        "vreau să vorbesc cu un om", "vreau sa vorbesc cu un om",
        "vreau să vorbesc cu septi", "vreau sa vorbesc cu septi",
        "vorbesc cu septi", "vorbesc cu cineva",
        "vorbesc cu o persoana", "vorbesc cu o persoană",
        "dați-mi pe septi", "dati-mi pe septi",
        "ia legatura cu septi", "ia legătura cu septi",
        "cheama-l pe septi", "cheamă-l pe septi",
        # Romanian — real person
        "om real", "un om real", "un om adevarat", "un om adevărat",
        "persoana reala", "persoana reală", "o persoana reala", "o persoană reală",
        "cineva real", "agent uman", "conecteaza-ma", "conectează-mă",
        # Romanian — complaints / refunds / urgent
        "reclamatie", "reclamație", "plangere", "plângere",
        "rambursare", "urgenta", "urgență",
    )

    # Sentences ending with these words are clearly cut off mid-thought.
    _INCOMPLETE_ENDINGS: frozenset[str] = frozenset({
        "i", "to", "for", "the", "a", "an", "and", "or", "but", "in", "at",
        "of", "on", "with", "by", "from", "about", "that", "my", "your", "is",
        "are", "was", "would", "want", "need", "just", "also", "ca",
        "să", "și", "că", "cu", "de", "la", "pe", "un", "o",
    })

    # 2-char words that are legitimate sentence endings and should not be
    # blocked by the short-last-word heuristic.
    _VALID_SHORT_ENDINGS: frozenset[str] = frozenset({
        "ok", "go", "no", "so", "do", "be", "uk", "us", "eu", "ro", "up",
    })

    # Phrases that signal the parent explicitly wants to enroll / sign up.
    # Intentionally narrow — asking about pricing, classes, age, schedule, etc.
    # is NOT enough. We only start intake when the parent says they actually
    # want to register. AI handles all informational questions naturally.
    _ENROLLMENT_SIGNALS: tuple[str, ...] = (
        # English — explicit signup/enrollment intent
        "sign up", "signup", "signing up", "sign me", "sign my",
        "enroll", "enrollment", "enrolment",
        "register",
        "want to join", "like to join", "i'd like to join", "would like to join",
        "interested in joining", "interested in signing", "interested in enrolling",
        "interested in registering", "interested in starting",
        "get started", "get my kid started", "get my child started",
        "how do i join", "how can i join",
        "how do i sign", "how can i sign",
        "how do i register", "how can i register",
        "how do i enroll", "how can i enroll",
        "i want to start", "i'd like to start",
        "join the program", "join the class", "join a class", "joining the",
        "want to start", "looking to join", "looking to sign", "looking to enroll",
        # Romanian
        "înscri", "inscri",
        "înregistra", "inregistra",
        "cum ma inscriu", "cum mă înscriu",
        "cum ma inregistrez", "cum mă înregistrez",
        "vreau sa ma inscriu", "vreau să mă înscriu",
        "vreau sa incep", "vreau să încep",
        "interesat să mă înscriu", "interesat sa ma inscriu",
        "interesat de înscriere", "interesat de inscriere",
    )

    _LEVEL_DISPLAY: dict[str, dict[str, str]] = {
        "beginner":     {"en": "Beginner",     "ro": "Începător"},
        "intermediate": {"en": "Intermediate", "ro": "Mediu"},
        "advanced":     {"en": "Advanced",     "ro": "Avansat"},
    }

    _NON_ANSWERS: frozenset[str] = frozenset({
        "idk", "idc", "idek", "dunno",
        "dont know", "don't know",
        "not sure", "no idea",
        "nu stiu", "nu știu", "habar nu am",
        "hm", "hmm", "huh", "lol",
    })

    # Phrases that should NEVER be accepted as a name answer — they're
    # conversational confirmations / filler, not an actual name.
    _NAME_NON_ANSWERS: frozenset[str] = frozenset({
        "ok", "okay", "ok go ahead", "okay go ahead",
        "go ahead", "sure", "sure go ahead", "yes", "yeah", "yep", "yup",
        "ready", "i'm ready", "im ready",
        "sounds good", "alright", "alright go ahead",
        "let's go", "lets go", "let's start", "lets start",
        "proceed", "continue",
        "da", "bine", "bine mergi", "hai",  # Romanian equivalents
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

    @staticmethod
    def _strip_questions(text: str) -> str:
        """Remove any question sentences from an AI response.

        Used as a safety net on ack_only and suppress_intake_questions responses
        so the AI can never duplicate the hardcoded question that follows.
        Splits on sentence-ending punctuation and drops every sentence that ends
        with '?'. Falls back to the original text if stripping would leave nothing.
        """
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        kept = [p for p in parts if p.strip() and not p.rstrip().endswith("?")]
        return " ".join(kept).strip() if kept else text.strip()

    def _lookup_city_timezone(self, text: str) -> str | None:
        lowered = text.lower()
        for city, tz in self._CITY_TIMEZONES.items():
            if re.search(r"\b" + re.escape(city) + r"\b", lowered):
                return tz
        return None

    def _is_valid_intake_answer(self, field: str, message: str) -> bool:
        text = message.lower().strip()

        # extra_notes and referral_source are free-form — any non-empty reply is acceptable
        if field in ("extra_notes", "referral_source"):
            return True

        if text in self._NON_ANSWERS:
            return False

        # Names must not be a generic confirmation phrase (exact match) OR
        # start with a confirmation word ("okay im ready ask whenever" → "okay").
        if field in ("parent_name", "child_name"):
            if text in self._NAME_NON_ANSWERS:
                return False
            first_word = text.split()[0] if text.split() else ""
            return first_word not in self._NAME_NON_ANSWERS

        if field == "child_age":
            return bool(re.search(r"\d", message))

        if field == "child_language_pref":
            normalized = self._normalize_intake_answer(field, message)
            return normalized in ("ro", "en", "both")

        if field == "group_pref":
            normalized = self._normalize_intake_answer(field, message)
            return normalized in CONSTRAINED_FIELD_VALUES[field]

        # demo_interest accepts any reply — normalization interprets yes/no/ambiguous
        if field == "demo_interest":
            return True

        return True

    # ------------------------------------------------------------------
    # Schedule & enrollment helpers
    # ------------------------------------------------------------------

    def _load_schedule(self) -> list[dict[str, Any]]:
        path = BASE_DIR / "schedule.json"
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f).get("classes", [])
        except (OSError, json.JSONDecodeError):
            return []

    def _save_enrollments(self) -> None:
        # Must be called while _leads_lock is held (directly or via _reply_locked).
        with self.enrollments_path.open("w", encoding="utf-8") as f:
            json.dump(self.enrollments, f, ensure_ascii=False, indent=2)

    def _class_has_space(self, cls: dict[str, Any]) -> bool:
        class_id = cls["id"]
        enrolled = sum(
            1 for records in self.enrollments.values()
            for e in records
            if e.get("class_id") == class_id and e.get("active", True)
        )
        return enrolled < cls.get("max_capacity", 6)

    def _get_available_classes(
        self, level: str, language: str, exclude_id: str | None = None
    ) -> list[dict[str, Any]]:
        return [
            c for c in self.schedule
            if c.get("active", True)
            and c.get("level", "").lower() == level.lower()
            and c.get("language", "").lower() == language.lower()
            and c.get("id") != exclude_id
            and self._class_has_space(c)
        ]

    def _get_class_by_id(self, class_id: str) -> dict[str, Any] | None:
        return next((c for c in self.schedule if c.get("id") == class_id), None)

    def _get_student_enrollments(self, phone: str) -> list[dict[str, Any]]:
        return [e for e in self.enrollments.get(phone, []) if e.get("active", True)]

    def _enroll_student(self, phone: str, child_name: str, class_id: str) -> None:
        if phone not in self.enrollments:
            self.enrollments[phone] = []
        for e in self.enrollments[phone]:
            if e.get("child_name", "").lower() == child_name.lower():
                e["active"] = False
        self.enrollments[phone].append({
            "child_name": child_name,
            "class_id": class_id,
            "enrolled_at": datetime.now(timezone.utc).isoformat(),
            "active": True,
        })
        self._save_enrollments()

    def _convert_class_time(
        self, time_str: str, class_tz: str, parent_tz: str | None
    ) -> str:
        try:
            from zoneinfo import ZoneInfo
            h, m = map(int, time_str.split(":"))
            src = ZoneInfo(class_tz)
            dst = ZoneInfo(parent_tz) if parent_tz else src
            today = datetime.now(timezone.utc).date()
            dt = datetime(today.year, today.month, today.day, h, m, tzinfo=src)
            dt_dst = dt.astimezone(dst)
            tz_label = parent_tz or class_tz
            return f"{dt_dst.strftime('%H:%M')} ({tz_label})"
        except Exception:
            return f"{time_str} ({class_tz})"

    def _format_class_options(
        self, classes: list[dict[str, Any]], parent_tz: str | None
    ) -> str:
        lines = []
        for i, cls in enumerate(classes, 1):
            time_display = self._convert_class_time(
                cls.get("time", ""), cls.get("timezone", "UTC"), parent_tz
            )
            lang_flag = "🇬🇧" if cls.get("language") == "en" else "🇷🇴"
            lines.append(
                f"{i}. {cls.get('day')} {time_display} — {cls.get('teacher')} {lang_flag}"
            )
        return "\n".join(lines)

    def _format_class_description(
        self, cls: dict[str, Any], parent_tz: str | None
    ) -> str:
        time_display = self._convert_class_time(
            cls.get("time", ""), cls.get("timezone", "UTC"), parent_tz
        )
        return f"{cls.get('day')} at {time_display} with {cls.get('teacher')}"

    def _filter_classes_by_availability(
        self, classes: list[dict[str, Any]], availability_text: str
    ) -> list[dict[str, Any]]:
        text = availability_text.lower()
        ro_to_en = {
            "luni": "monday", "marti": "tuesday", "marți": "tuesday",
            "miercuri": "wednesday", "joi": "thursday", "vineri": "friday",
            "sambata": "saturday", "sâmbătă": "saturday",
            "duminica": "sunday", "duminică": "sunday",
        }
        days: set[str] = set()
        _weekdays = {"monday", "tuesday", "wednesday", "thursday", "friday"}
        _weekend = {"saturday", "sunday"}
        if "weekend" in text or "sfarsit de saptamana" in text or "sfârșit de săptămână" in text:
            days.update(_weekend)
        if any(w in text for w in ("weekday", "week day", "zilele saptamanii", "zilele săptămânii", "in timpul saptamanii", "în timpul săptămânii")):
            days.update(_weekdays)
        for ro, en in ro_to_en.items():
            if ro in text:
                days.add(en)
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"):
            if day in text:
                days.add(day)
        if not days:
            return classes
        filtered = [c for c in classes if c.get("day", "").lower() in days]
        return filtered if filtered else classes

    def _normalize_level(self, message: str) -> str | None:
        text = message.lower()
        if any(w in text for w in (
            "beginner", "începător", "incepator", "newbie", "never played",
            "n-a jucat", "nu a jucat", "just starting", "abia", "1", "one", "unu",
        )):
            return "beginner"
        if any(w in text for w in (
            "intermediate", "mediu", "some experience", "knows basics",
            "știe regulile", "stie regulile", "a mai jucat", "2", "two", "doi",
        )):
            return "intermediate"
        if any(w in text for w in (
            "advanced", "avansat", "experienced", "very good", "foarte bun",
            "plays tournaments", "joacă turnee", "joaca turnee", "3", "three", "trei",
        )):
            return "advanced"
        return None

    def _parse_class_selection(
        self, message: str, options: list[str]
    ) -> str | None:
        text = message.lower().strip()
        m = re.search(r"\b([1-4])\b", text)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(options):
                return options[idx]
        day_aliases: dict[str, str] = {
            "monday": "monday", "luni": "monday",
            "tuesday": "tuesday", "marti": "tuesday", "marți": "tuesday",
            "wednesday": "wednesday", "miercuri": "wednesday",
            "thursday": "thursday", "joi": "thursday",
            "friday": "friday", "vineri": "friday",
            "saturday": "saturday", "sambata": "saturday", "sâmbătă": "saturday",
            "sunday": "sunday", "duminica": "sunday", "duminică": "sunday",
        }
        for alias, day_en in day_aliases.items():
            if alias in text:
                for opt_id in options:
                    cls = self._get_class_by_id(opt_id)
                    if cls and cls.get("day", "").lower() == day_en:
                        return opt_id
        return None

    def _handle_lead_intake(self, message: str, phone: str) -> str | list[str] | None:
        lead = self._get_lead(phone)

        if lead is not None and lead.get("stage") == "faq_only":
            # If the parent comes back and clearly wants to enroll a second child,
            # reset intake so we can collect fresh info for the new child.
            _second_child_signals = (
                "second child", "another child", "my other kid", "other kid",
                "second kid", "younger one", "older one", "sibling",
                "my son too", "my daughter too", "him too", "her too",
                "al doilea copil", "un alt copil", "celalalt copil", "celălalt copil",
                "si pentru el", "și pentru el", "si pentru ea", "și pentru ea",
                "si fiul", "și fiul", "si fiica", "și fiica",
            )
            lang = lead.get("lang", "ro")
            if any(sig in message.lower() for sig in _second_child_signals) or (
                any(sig in message.lower() for sig in self._ENROLLMENT_SIGNALS)
                and any(w in message.lower() for w in ("also", "too", "as well", "another", "second", "si", "și", "alt", "și"))
            ):
                existing_parent_name = lead.get("parent_name")
                lead["stage"] = "intake_in_progress"
                lead["collected_fields"] = ["parent_name"] if existing_parent_name else []
                lead["nudge_sent"] = False
                lead["post_intake_nudge_sent"] = False
                lead["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save_leads()
                if lang == "ro":
                    restart_msg = "Sigur, hai să completăm datele pentru cel de-al doilea copil 🙂"
                else:
                    restart_msg = "Of course, let's go through the details for your second child 🙂"
                first_q = "child_name" if existing_parent_name else "parent_name"
                return [restart_msg, INTAKE_QUESTIONS[first_q][lang]]

            # Parent in faq_only asks to sign up (e.g. explored FAQs first, now ready).
            # Restart intake so we can collect their details properly.
            if any(sig in message.lower() for sig in self._ENROLLMENT_SIGNALS):
                existing_parent_name = lead.get("parent_name")
                lead["stage"] = "intake_in_progress"
                lead["collected_fields"] = ["parent_name"] if existing_parent_name else []
                lead["handed_off"] = False
                lead["demo_interest"] = None
                lead["nudge_sent"] = False
                lead["post_intake_nudge_sent"] = False
                lead["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save_leads()
                if self.ai_enabled:
                    ai_response = self._strip_questions(
                        self._ai_reply(message, phone, suppress_intake_questions=True)
                    )
                    first_q = "child_name" if existing_parent_name else "parent_name"
                    return [ai_response, INTAKE_QUESTIONS[first_q][lang]]
                first_q = "child_name" if existing_parent_name else "parent_name"
                return [self._pick(INTAKE_TRANSITION, lang), INTAKE_QUESTIONS[first_q][lang]]

            return None

        # Enrolled parents — no structured scheduling flow; fall through to AI
        if lead is not None and lead.get("stage") == "enrolled":
            return None

        lang = detect_language(message)
        # For North American numbers, default to English when language is ambiguous
        # so a Canadian French speaker at least gets English rather than Romanian.
        if lang == "ro":
            bucket, _ = infer_currency_bucket(phone)
            if bucket in ("USD", "CAD"):
                lang = "en"

        if lead is None:
            lead = self._create_lead(phone, lang, initial_stage="greeted")
            self._save_leads()
            # Pure greeting → introduce ourselves and wait to see what they need
            if message.lower().strip() in self._GREETING_WORDS:
                if self.ai_enabled:
                    return self._ai_reply(message, phone, intake_context={"is_intro": True})
                return self._pick(GREETING_INTRO, lang)
            # Substantive first message → fall through to greeted-stage logic below
            # so we actually respond to what they said instead of ignoring it

        lang = lead.get("lang", "ro")

        if lead.get("stage") == "greeted":
            # Saying hello mid-conversation → just say hi back
            if message.lower().strip() in self._GREETING_WORDS:
                return self._pick(GREETING_REPLY, lang)

            # Try rule-based first — handoffs and booking lookups must always go through
            # regardless of enrollment signals. Other rule answers (social media, teachers,
            # etc.) are NOT returned here; the enrollment check below decides what happens
            # next, and if no signal fires, the outer reply() picks them up.
            rule_answer = self._rule_based_reply(message, phone)
            terminal_flat = [
                v
                for pool in (HANDOFF_VARIANTS,)
                for variants in pool.values()
                for v in variants
            ]
            if rule_answer and rule_answer in terminal_flat:
                return rule_answer

            # Pricing question — ask country first so we quote the right currency.
            # Store the original question and answer it once country is known.
            if lead.get("pending_pricing"):
                original_q = lead.pop("pending_pricing")
                new_bucket = self._infer_currency_from_country(message)
                if new_bucket:
                    lead["currency_bucket"] = new_bucket
                lead["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save_leads()
                if self.ai_enabled:
                    return self._ai_reply(original_q, phone)
                return None

            if self._contains_any(message.lower(), self._PRICING_QUESTION_HINTS):
                # If the parent already mentioned their country in the same message,
                # use it directly instead of asking again.
                bucket_from_msg = self._infer_currency_from_country(message)
                if bucket_from_msg:
                    lead["currency_bucket"] = bucket_from_msg
                    lead["updated_at"] = datetime.now(timezone.utc).isoformat()
                    self._save_leads()
                    if self.ai_enabled:
                        return self._ai_reply(message, phone)
                    return None
                lead["pending_pricing"] = message
                lead["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save_leads()
                return self._pick(PRICING_NEEDS_COUNTRY, lang)

            # Only transition to intake when the message clearly signals enrollment interest.
            text = message.lower()
            has_signal = any(sig in text for sig in self._ENROLLMENT_SIGNALS)
            if not has_signal:
                # Let the AI (or outer rule) answer naturally; stay in greeted stage.
                return None

            # Clear enrollment intent — start intake.
            lead["stage"] = "intake_in_progress"
            self._save_leads()

            # Let AI respond to what the user actually said (may include info
            # questions alongside the signup intent), then send the first intake
            # question as a separate follow-up message so nothing gets ignored.
            if self.ai_enabled:
                ai_response = self._strip_questions(
                    self._ai_reply(message, phone, suppress_intake_questions=True)
                )
                return [ai_response, INTAKE_QUESTIONS["parent_name"][lang]]

            # No AI available — fall back to the hardcoded transition.
            return self._pick(INTAKE_TRANSITION, lang)

        # stage == "intake_in_progress"

        # Greeting mid-intake — if returning after a gap, acknowledge warmly before
        # picking up where they left off; otherwise just re-ask the pending question.
        if message.lower().strip() in self._GREETING_WORDS:
            pending_field = self._next_missing_field(lead)
            if pending_field:
                q = INTAKE_QUESTIONS[pending_field][lang]
                if self.ai_enabled:
                    return [self._ai_reply(message, phone, intake_context={
                        "is_greeting": True,
                        "is_returning": self._is_returning_lead(lead),
                        "fields_done": len(lead.get("collected_fields", [])),
                        "next_field": pending_field,
                        "next_question": q,
                    })]
                if self._is_returning_lead(lead):
                    fields_done = len(lead.get("collected_fields", []))
                    if lang == "en":
                        welcome = f"Hey, welcome back 🙂 You were {fields_done} question{'s' if fields_done != 1 else ''} into signing up"
                    else:
                        welcome = f"Bună, bine ai revenit 🙂 Erai la întrebarea {fields_done + 1} din înregistrare"
                    return [welcome, q]
                opener = random.choice(
                    ["Hey! 🙂 ", "Hi! 🙂 ", "Hey there! "] if lang == "en"
                    else ["Bună! 🙂 ", "Salut! 🙂 ", "Hey! 🙂 "]
                )
                return f"{opener}{q}"
            return None

        pending_field = self._next_missing_field(lead)

        if pending_field is None:
            return None

        # Correction — parent wants to update a previously given answer.
        # Scan all already-collected fields for a new extractable value, update silently,
        # then let AI acknowledge the change naturally.
        _CORRECTION_PHRASES = ("actually", "wait,", "correction,", "i meant", "i mean,", "sorry,", "oops", "my bad")
        if self._contains_any(message.lower(), _CORRECTION_PHRASES):
            for field in REQUIRED_INTAKE_FIELDS:
                if field in lead.get("collected_fields", []):
                    extracted = self._try_extract_field(field, message)
                    if extracted is not None and extracted != lead.get(field):
                        lead[field] = self._normalize_intake_answer(field, extracted)
                        lead["updated_at"] = datetime.now(timezone.utc).isoformat()
                        self._save_leads()
            return None  # Let AI respond naturally ("Got it, updated!")

        # Opt-out — parent changed their mind or wants to pause.
        # Reset to greeted so they can come back later without losing what they shared.
        if self._contains_any(message.lower(), self._OPT_OUT_PHRASES):
            lead["stage"] = "greeted"
            self._save_leads()
            return None  # Let AI respond warmly

        # extra_notes and referral_source accept any reply — don't let rule-based
        # handlers steal them (e.g. "Thanks, nothing else" triggers the thanks handler).
        # For all other fields, only treat the message as a FAQ question if it actually
        # looks like one — starts with a question word or ends with "?". This prevents
        # bare keywords like "kids", "bus", "cancel" inside a normal intake answer
        # (e.g. "weekdays when the kids get home") from triggering FAQ rules.
        _question_starters = (
            "what", "how", "when", "where", "why", "who", "which",
            "is ", "are ", "can ", "do ", "does ", "did ", "will ",
            "ce ", "cum ", "când ", "cand ", "unde ", "cine ", "care ",
            "este ", "sunt ", "pot ", "puteți ", "puteti ",
        )
        msg_lower = message.lower().strip()
        looks_like_question = (
            message.strip().endswith("?")
            or any(msg_lower.startswith(w) for w in _question_starters)
        )
        if pending_field not in ("extra_notes", "referral_source", "demo_interest") and looks_like_question and (
            self._rule_based_reply(message, phone) or self._mentions_ai_topic(message)
        ):
            return None

        # Reject answers that don't make sense for the question being asked.
        # Bare digits count as length-1 so skip the length check for child_age;
        # all other fields need at least 2 alphanumeric characters.
        alphanum = re.sub(r"[^a-zA-Z0-9]", "", message)
        too_short = pending_field != "child_age" and len(alphanum) < 2
        if too_short or not self._is_valid_intake_answer(pending_field, message):
            if self.ai_enabled:
                return [self._ai_reply(message, phone, intake_context={
                    "next_field": pending_field,
                    "next_question": INTAKE_QUESTIONS[pending_field][lang],
                    "re_asking": True,
                })]
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

        # Sep7Ro classes are for children ages 6–11 only.
        if pending_field == "child_age":
            age_match = re.search(r"\b(\d+)\b", message)
            if age_match:
                age = int(age_match.group(1))
                if age >= 18:
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
                if age < 6:
                    if lang == "en":
                        return (
                            "Our chess program starts from age 6 🙂 "
                            "Feel free to reach out again closer to their 6th birthday and we'll find a great group for them"
                        )
                    else:
                        return (
                            "Programul nostru de șah începe de la 6 ani 🙂 "
                            "Reveniți când se apropie de 6 ani și găsim o grupă potrivită pentru ei"
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
            if self.ai_enabled:
                # AI only acknowledges what the parent said — the hardcoded next question
                # is always appended as a separate message so the AI can never skip fields,
                # combine questions, or ask something different.
                # _strip_questions is a hard safety net: if the AI still sneaks a question
                # into the ack, we remove it before the user ever sees it.
                ai_ack = self._strip_questions(self._ai_reply(message, phone, intake_context={
                    "just_collected": pending_field,
                    "ack_only": True,
                }))
                return [ai_ack, INTAKE_QUESTIONS[next_field][lang]]
            return [self._pick(INTAKE_ACK, lang), INTAKE_QUESTIONS[next_field][lang]]

        lead["stage"] = "faq_only"
        # Treat anything other than an explicit "no" as interested — benefit of the doubt
        # (covers "can he get back to you?", "maybe", "sure", "yes", etc.)
        demo_yes = lead.get("demo_interest") != "no"
        lead["handed_off"] = demo_yes
        self._save_leads()
        if demo_yes:
            self._maybe_notify_staff(phone, lead)
        if self.ai_enabled:
            return self._ai_reply(message, phone, intake_context={"is_closing": True, "demo_interested": demo_yes})
        if demo_yes:
            return self._pick(CLOSING_MESSAGE, lang)
        # Declined the demo — close warmly without Septi notification
        if lang == "en":
            return "No worries at all 🙂 If you ever change your mind, we're always here whenever you're ready"
        return "Nicio problemă 🙂 Dacă te răzgândești, suntem mereu aici oricând ești gata"

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
            if self.ai_enabled:
                return None
            return self._pick(GREETING_REPLY, lang)

        if self._contains_any(
            text,
            ("thank you", "thanks", "thx", "multumesc", "mulțumesc", "mersi"),
        ):
            if self.ai_enabled:
                return None
            return self._pick(THANKS_REPLY, lang)

        if self._contains_any(text, self._THINKING_IT_OVER_PHRASES):
            if self.ai_enabled:
                return None
            return self._pick(THINKING_IT_OVER, lang)

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
            if self.ai_enabled:
                return None
            return self._pick(HELP_REPLY, lang)

        if self._contains_any(
            text,
            (
                "more information", "more info", "give me info",
                "tell me more", "tell me about", "what is sep7ro",
                "about the program", "about the school", "about sep7ro",
                "what do you offer", "what does sep7ro offer",
                "mai multe informatii", "mai multe info",
                "mai mult despre", "despre program", "despre scoala", "despre școală",
                "ce este sep7ro", "ce oferiti", "ce oferiți",
                "puteti sa mi dati", "puteți să îmi dați", "mai multe detalii",
            ),
        ):
            if self.ai_enabled:
                return None
            paragraphs = self.company_data.get("program_overview", {}).get(lang, [])
            if paragraphs:
                return "\n\n".join(paragraphs)

        # Human-request signals are handled upstream in _reply_locked (pre-check),
        # which also notifies Septi. This fallback only fires if _rule_based_reply is
        # called outside of _reply_locked (e.g. mid-intake FAQ check).
        if self._is_human_request(message):
            if self.ai_enabled:
                return None
            return self._handoff(lang)

        # Signup/enrollment phrases are handled by the intake flow (_ENROLLMENT_SIGNALS
        # in _handle_lead_intake), not by a static fallback reply here.

        # All remaining FAQ handlers are informational — let AI answer when enabled.
        if self.ai_enabled:
            return None

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
                    "class availab",
                    "availab",
                    "available slots",
                    "available times",
                    "when can",
                    "what slots",
                    "what time slots",
                    "orarul claselor",
                    "ce zile",
                    "ce ore",
                    "cand sunt clasele",
                    "când sunt clasele",
                    "disponibilitate",
                    "sloturi disponibile",
                    "cand pot",
                    "când pot",
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

    def _ai_reply(self, message: str, sender_phone: str, *, suppress_intake_questions: bool = False, intake_context: dict | None = None) -> str:
        assert self.client is not None

        phone = self._normalize_phone(sender_phone)
        lead = self._get_lead(phone)
        # Use the lead's stored language when available — terse intake answers like
        # "7" or "Ana" have no language markers and would otherwise default to English.
        lang = lead.get("lang") if lead else detect_language(message)
        if not lang:
            lang = detect_language(message)

        # Prefer the currency we set from the parent's stated country over the
        # phone-prefix guess — a Romanian-number parent living in the UK should
        # see GBP, not RON. Also covers the pending_pricing flow where the parent
        # answered "what country are you in?" but hasn't completed the full intake.
        phone_bucket, phone_country_code = infer_currency_bucket(sender_phone)
        if lead and lead.get("currency_bucket") and lead["currency_bucket"] != phone_bucket:
            # Parent explicitly told us their country; trust that over the phone prefix.
            currency_bucket = lead["currency_bucket"]
            country_code = True
        elif lead and "country" in lead.get("collected_fields", []):
            currency_bucket = lead["currency_bucket"]
            country_code = True
        else:
            currency_bucket, country_code = phone_bucket, phone_country_code

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

        assistant_name = self.company_data.get("assistant_name", "Alex")
        follow_up_window = self.company_data.get("follow_up_window", "within 24 hours")

        intake_done_note = ""
        if lead and lead.get("stage") == "faq_only":
            intake_done_note = (
                f"\nContext: This parent has already completed the enrollment form. "
                f"Septi has been notified and will reach out {follow_up_window} to "
                f"schedule the free 50-minute demo lesson. If the parent asks what happens "
                f"next, what they should do, or when Septi will contact them, tell them "
                f"exactly that: Septi will reach out {follow_up_window} to set up the demo. "
                f"Do NOT offer to check availability or make promises about specific times. "
                f"Do NOT imply you will personally follow up or do anything further.\n"
            )

        intake_starting_note = ""
        if suppress_intake_questions:
            intake_starting_note = (
                "\nTask: The parent just expressed interest in enrolling their child. "
                "Write a warm, brief welcome (1-2 sentences max). Acknowledge that you'll "
                "collect a few details to get them set up. Do NOT mention the demo lesson, "
                "do NOT describe the enrollment process. "
                "CRITICAL: Do NOT ask ANY question at all — not about name, age, country, "
                "availability, experience, or anything else. A separate question will be "
                "sent automatically right after your message. Your message must end with a "
                "statement or exclamation, never a question mark.\n"
            )

        intake_context_note = ""
        if intake_context:
            if intake_context.get("is_intro"):
                intake_context_note = (
                    f"\nTask: A parent just said hello for the first time. "
                    f"Introduce yourself: you are {assistant_name}, Septi's assistant at Sep7Ro. "
                    f"Keep it warm and brief (1-2 sentences), then invite them to ask anything or "
                    f"let them know you can help with info about the chess program. "
                    f"Do NOT ask any questions.\n"
                )
            elif intake_context.get("is_closing"):
                if intake_context.get("demo_interested"):
                    intake_context_note = (
                        "\nTask: The parent just finished providing all their enrollment info and said yes to the demo lesson. "
                        "Write a warm, brief closing message (1-2 sentences). Confirm everything is in "
                        "and that Septi will reach out within 24 hours to schedule the free demo. "
                        "No questions at the end.\n"
                    )
                else:
                    intake_context_note = (
                        "\nTask: The parent just finished providing their info but declined the free demo lesson. "
                        "Write a warm, brief closing message (1-2 sentences). Thank them sincerely, "
                        "let them know the door is always open if they change their mind. "
                        "No questions at the end.\n"
                    )
            elif intake_context.get("is_greeting"):
                next_q = intake_context.get("next_question", "")
                if intake_context.get("is_returning"):
                    fields_done = intake_context.get("fields_done", 0)
                    intake_context_note = (
                        f"\nTask: The parent is returning after a gap (they had answered "
                        f"{fields_done} enrollment question{'s' if fields_done != 1 else ''} already). "
                        f"Greet them warmly, acknowledge they're picking up where they left off, "
                        f"and ask: {next_q}\n"
                    )
                else:
                    intake_context_note = (
                        f"\nTask: The parent just said hello while you're mid-intake. "
                        f"Respond warmly and ask: {next_q}\n"
                    )
            elif intake_context.get("re_asking"):
                next_q = intake_context.get("next_question", "")
                intake_context_note = (
                    f"\nTask: The parent's last message didn't clearly answer the question you asked. "
                    f"First, actually respond to what they said — if they said 'Idk', help them think "
                    f"through it ('even a rough idea works 🙂'); if they went off-topic, acknowledge it "
                    f"first; if they seem unsure, reassure them. Never say 'I didn't catch that' or "
                    f"anything robotic like that. Then re-ask naturally in a different way: {next_q}\n"
                )
            elif intake_context.get("ack_only"):
                just_collected = intake_context.get("just_collected", "").replace("_", " ")
                intake_context_note = (
                    f"\nTask: You just received the parent's {just_collected}. "
                    f"React to what they said naturally — if they made a joke, laugh along; "
                    f"if they asked something, answer it; if they said something worth "
                    f"acknowledging, do so warmly. "
                    f"CRITICAL: Do NOT ask any question at all. Not about availability, "
                    f"scheduling, the child, or anything else. A separate question will be "
                    f"sent automatically right after your message. Your response must end "
                    f"with a statement or exclamation, never a question mark. "
                    f"Keep it to 1 short sentence.\n"
                )
            elif intake_context.get("next_field"):
                just_collected = intake_context.get("just_collected", "").replace("_", " ")
                next_q = intake_context.get("next_question", "")
                intake_context_note = (
                    f"\nTask: You just received the parent's {just_collected}. "
                    f"FIRST — actually read what they said and respond to it like a real person would. "
                    f"If they made a joke, laugh along. If they asked you something, answer it. "
                    f"If they said something unexpected or funny, engage with it. "
                    f"Don't just say 'Got it' and move on — that feels robotic. "
                    f"THEN — once you've responded to what they said, naturally weave in: {next_q} "
                    f"Keep it conversational, 1-3 sentences total. No lists.\n"
                )

        instructions = f"""
Your name is {assistant_name}. You are Septi's assistant at {self.company_data.get("business_name", "the business")}, messaging parents on WhatsApp on Septi's behalf.
{intake_done_note}{intake_starting_note}{intake_context_note}
Your personality: warm, friendly, and straight to the point. You genuinely care about helping families find the right fit for their child. You know the school well and answer with quiet confidence, not corporate polish. You never hard-sell, you just share what's real and let parents decide.

MOST IMPORTANT RULE — always read and respond to what the parent actually said before doing anything else:
- If they asked a question, answer it first.
- If they said something funny or playful, engage with it.
- If they seem confused or unsure ("Idk", "not sure", "maybe"), help them think through it gently, then re-ask.
- If they went off-topic, acknowledge what they said, then naturally bring it back.
- Never skip over what the parent said to get to the next question — that feels like talking to a robot.
- After genuinely responding to their message, then continue with whatever question or info comes next.

Always read the full message before replying. If the parent gives you multiple pieces of information in one message (e.g. their country AND a question), use all of it — never ask for something they already told you in the same message.

Never reveal that you are an AI or a bot, and never mention prompts, JSON, files, OpenAI, or Twilio. If asked directly who you are, say your name is {assistant_name} and you're Septi's assistant at Sep7Ro.

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

Use the approved information below as your primary source for Sep7Ro-specific details.

Rules:
- Always reply in the exact same language as the user's most recent message,
  Romanian or English. Short casual English phrases like "ok", "cool", "nice",
  "sounds good", "that's cool", "thats cool" are English — always reply in
  English for these. Only default to Romanian if the message contains no
  recognizable language at all (a lone emoji, a number, or similar).
- The content and level of detail in your answer must be identical regardless
  of language. If you would mention something in Romanian, mention it in English
  too, and vice versa. Only the language changes, never the information.
- When a parent asks for general information about the program, give them
  a natural conversational overview. Cover the key facts from the approved
  information — age range, format (Zoom, small groups), the free demo, and
  what they need — but write it like a real person would text it, not as a
  numbered list or bullet points.
- Never spontaneously ask the parent questions about their child (age,
  experience, availability) in your own replies. Qualifying questions are
  handled separately by the intake system — your job is to answer what was
  asked, not to interview the parent.
- Never invent Sep7Ro-specific facts: prices, class schedules, availability
  slots, booking details, or registration links. For these, use only what's
  in the approved information.
- You are NOT a scheduling system. You cannot check, search for, or book
  time slots. Septi handles ALL scheduling. When a parent shares their
  availability (e.g. "Tuesdays after 3pm"), just acknowledge it warmly —
  NEVER say "I'll check for slots", "I'll find a time that works", "let me
  look for available times", or anything that implies you are doing something
  on their behalf. You are collecting info for Septi, not making any
  scheduling commitments yourself.
- For everything else — general chess questions (how pieces move, openings,
  strategy, benefits of chess for kids, how to practice at home), Lichess
  tips, child learning and development, or anything a knowledgeable chess
  school assistant would naturally know — answer confidently from your own
  knowledge. Never deflect a reasonable question just because it's not in
  the approved info. The goal is to always be genuinely useful.
- Treat values containing the word REPLACE as missing. For these, give the
  most helpful general answer you can, then mention Septi can confirm the
  specific details when he reaches out.
- {currency_note}
- Never volunteer prices or discounts unless the parent explicitly asks about
  cost, pricing, fees, or how much it is. If they ask for general information
  about the program, describe what the school offers — classes, format, age
  range, demo lesson — without mentioning any numbers. Let them ask about price
  when they're ready.
- The sibling discount (25%) and twin discount (50%) must NEVER be mentioned
  unless the parent themselves (not you in a prior message) has explicitly said
  they have more than one child looking to enroll — words like "I have two kids",
  "siblings", "twins", or asking specifically about discounts for multiple children.
  Do not infer this from your own previous messages. If in doubt, leave it out.
- Never share any other family's, child's, or lead's personal information.
  You don't have access to anyone else's records, only this approved
  business information.
- Do not claim that a customer has successfully registered.
- If someone asks HOW to sign up, says they want to sign up, or expresses enrollment
  intent ("how can I sign up", "I want to register", "how do I enroll"), do NOT send
  a registration link. Instead, tell them warmly that you'll walk them through a few
  quick questions to get them set up. The intake system will collect their details.
- Only give the registration link if the parent explicitly asks for "the link" or
  "the registration link" itself.
- If someone says they want to think about it, need more time, or sends
  a low-commitment conversational reply ("sounds good", "ok thanks",
  "I'll think about it", "can I think about it?", "maybe later",
  "I'll let you know", "not sure yet") — respond warmly and briefly.
  A short encouraging reply is perfect. Do NOT treat these as unclear
  questions or trigger the handoff. Example: "Of course, take your time
  🙂 I'm here whenever you're ready"
- Never say you didn't understand a question that is clearly intelligible.
  If you're unsure about a Sep7Ro-specific detail, answer with what you
  do know and bridge to the next step naturally.
- When the user sends a casual conversational message ('ok', 'cool', 'thats cool', 'nice', 'got it', 'sounds good', 'interesting', 'makes sense', 'sure', 'awesome' etc.), respond naturally and warmly — keep it brief, then invite them to ask more or get started. Never deflect casual small talk to Septi.
- Only hand off to Septi for: complaints, refund requests,
  emergencies, or explicit requests to speak to a real person.
  For those, write a short warm message saying Septi is the right
  person to help and they can reach out to him directly. For
  everything else — answer it yourself.

APPROVED INFORMATION:
{approved_information}
""".strip()

        phone = self._normalize_phone(sender_phone)
        if phone not in self._conversation_history and self._db_available:
            loaded = db.load_history(phone)
            if loaded:
                self._conversation_history[phone] = loaded
        prior = self._conversation_history.get(phone, [])
        input_messages = [*prior, {"role": "user", "content": message}]

        try:
            response = self.client.responses.create(
                model=self.model,
                instructions=instructions,
                input=input_messages,
            )

            answer = response.output_text.strip()
            # Strip a lone trailing period the AI occasionally adds
            if answer.endswith(".") and not answer.endswith("..."):
                answer = answer[:-1]
            return answer or self._handoff(lang)

        except Exception as exc:
            print(f"[AI ERROR] {type(exc).__name__}: {exc}")
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

        # A message ending in "?" is a complete question regardless of the last word.
        if message.strip().endswith("?"):
            return True

        # Ends mid-thought (e.g. "id like to s", "id like to si", "I want")
        words = message.lower().split()
        last = re.sub(r"[^a-zA-ZăîâșțĂÎÂȘȚ]", "", words[-1]) if words else ""
        if last in self._INCOMPLETE_ENDINGS:
            return False
        if len(last) <= 2 and last not in self._VALID_SHORT_ENDINGS:
            return False

        return True

    def reply(self, message: str, sender_phone: str) -> list[str]:
        with self._leads_lock:
            return self._reply_locked(message, sender_phone)

    def _reply_locked(self, message: str, sender_phone: str) -> list[str]:
        phone = self._normalize_phone(sender_phone)
        lead = self._get_lead(phone)

        # /resetchat — wipe this user's lead and conversation history.
        # Done inline (not via clear_lead) because _reply_locked already holds _leads_lock.
        if message.strip().lower() == "/resetchat":
            self.leads.pop(phone, None)
            self._conversation_history.pop(phone, None)
            if self._db_available:
                db.delete_lead(phone)
                db.delete_history(phone)
            self._save_leads()
            return ["Chat reset 🙂 Let's start fresh — how can I help you?"]

        # Any new message clears the "thinking it over" waiting state
        if lead is not None and lead.get("thinking_it_over"):
            lead["thinking_it_over"] = False
            lead["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save_leads()

        # Keep the stored language in sync with the user's current message so the
        # bot follows if they switch languages (e.g. from Romanian to English).
        # Skip during active intake so terse answers like "Ana" or "7" don't flip it.
        if lead is not None and lead.get("stage") != "intake_in_progress":
            current_lang = detect_language(message)
            if current_lang != lead.get("lang"):
                lead["lang"] = current_lang
                lead["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save_leads()

        # Check intelligibility before doing anything — but not mid-intake,
        # where terse answers like "english" or "7" are expected and valid.
        # When AI is enabled, skip this entirely — OpenAI handles anything gracefully.
        in_intake = lead is not None and lead.get("stage") == "intake_in_progress"
        if not self.ai_enabled and not in_intake and not self._is_intelligible(message):
            lang = lead.get("lang", "ro") if lead else detect_language(message)
            unclear = self._pick(UNCLEAR_INPUT, lang)
            self._append_to_history(phone, message, unclear)
            return [unclear]

        # Pre-check: explicit request to speak to a human — intercepts even mid-intake.
        if self._is_human_request(message):
            lang = lead.get("lang", detect_language(message)) if lead else detect_language(message)
            if lead is None:
                lead = self._create_lead(phone, lang, initial_stage="greeted")
            # Notify Septi once per hour — prevents spam from duplicate webhooks or
            # repeated asks, but fires again if the same person comes back later.
            last_notified_str = lead.get("human_request_notified_at")
            should_notify = True
            if last_notified_str:
                try:
                    last_notified = datetime.fromisoformat(last_notified_str)
                    should_notify = (datetime.now(timezone.utc) - last_notified) > timedelta(hours=1)
                except ValueError:
                    pass
            if should_notify:
                lead["human_requested"] = True
                lead["human_request_notified_at"] = datetime.now(timezone.utc).isoformat()
                lead["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save_leads()
                self._notify_human_request(phone, lead)
            if self.ai_enabled:
                reply_text = self._ai_reply(message, sender_phone)
            else:
                reply_text = self._handoff(lang)
            self._append_to_history(phone, message, reply_text)
            return [reply_text]

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
                _lang = lead.get("lang", detect_language(message)) if lead else detect_language(message)
                reply_text = self._handoff(_lang)
            parts = [reply_text]

        _thinking_triggered = (
            lead is not None
            and lead.get("stage") != "intake_in_progress"
            and self._contains_any(message.lower(), self._THINKING_IT_OVER_PHRASES)
        )

        # If the reply was a "thinking it over" acknowledgement, mark for 48h follow-up
        if _thinking_triggered and lead is not None:
            lead["thinking_it_over"] = True
            lead["thinking_it_over_at"] = datetime.now(timezone.utc).isoformat()
            lead["thinking_it_over_nudge_sent"] = False
            lead["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save_leads()

        self._append_to_history(phone, message, "\n\n".join(parts))

        return parts