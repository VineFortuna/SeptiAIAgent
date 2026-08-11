# Sep7Ro WhatsApp Assistant

This project receives WhatsApp messages through Twilio and responds as Septi, the founder of Sep7Ro chess school, with:

- a lead-intake conversation for new contacts that collects the details Septi needs (name, country, timezone, child's age/experience/availability, group preference, etc.), with a WhatsApp notification to staff once it's done
- approved class information from `company_data.json` (pricing, schedule, policies, links)
- a class registration link
- a handoff to Septi when the parent explicitly asks for a person, or raises a complaint/refund/emergency

Every reply goes through OpenAI — there's no keyword-matching fallback mode. Two things route it: an **orchestrator** that decides which conversation flow handles the message (`intake` or `faq`), and that flow's own prompt file under `flows/`. Each flow only sees its own conversation history, and replies stay in character as Septi's assistant (no disclosure that it's automated, by explicit request). See "Editing how the bot talks" below for how to change its behavior without touching Python.

## 1. Install Python on Windows

Install a current Python 3 release from the official Python website. During installation, enable **Add Python to PATH**.

Open PowerShell and check:

```powershell
python --version
```

## 2. Open this folder in PowerShell

Example:

```powershell
cd "$HOME\Downloads\whatsapp-class-assistant"
```

## 3. Create the virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks the activation script, run this once in the same window:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 4. Create the settings file

```powershell
Copy-Item .env.example .env
```

Do not publish `.env`, API keys, or Twilio credentials to GitHub.

## 5. Test without WhatsApp first

```powershell
python chat_demo.py
```

Try these messages (works in English or Romanian — try both):

```text
Where are you located?
Does my child need experience?
What classes do you offer?
Can I sign up for a class?
Can I talk to a staff member?

Unde sunteti?
Are nevoie de experienta?
Ce clase aveti?
```

Any phone number is treated as a new lead until it explicitly signals it wants to enroll (e.g. "Can I sign up for a class?" or "I'd like to sign up my son") — that's when the intake conversation starts. Use e.g. `+40733445566` to see it.

## 6. Add company information

Open `company_data.json` — one canonical fact per field (pricing, schedule, policies, links). The bot translates and rephrases it on the fly, so don't duplicate facts per language or write multiple phrasings; just state the fact once, plainly. A handful of fields are still placeholder strings starting with `REPLACE` because that information hasn't been provided yet: `registration_link`, `contact_phone`, `contact_email`, `payment_methods`, `late_arrival_policy`. Fill those in with real values once available — until then, the bot correctly says it'll check and get back to you rather than guessing.

Do not enter customer passwords, payment details, medical information, or other unnecessary sensitive information.

## 6a. Editing how the bot talks

There's no Python to edit for conversation behavior — everything lives in `flows/`:

- `orchestrator_prompt.txt` — decides whether an incoming message belongs to `intake` or `faq`.
- `intake_prompt.txt` — what the bot collects from a new lead, and how it talks while doing it.
- `faq_prompt.txt` — tone rules and how it uses `company_data.json` to answer questions.
- `nudge_prompt.txt` — used for the proactive follow-up messages (see section 7b).

Each is a short, plain-English instruction file — edit the wording directly and the next message picks it up immediately, no restart needed. Keep them concise: everything in a flow's prompt file (plus `company_data.json` for `faq_prompt.txt`) is sent to OpenAI on every message that flow handles, so shorter is cheaper.

## 7. Add OpenAI

Create an OpenAI API key and place it in `.env`:

```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4o
OPENAI_ORCHESTRATOR_MODEL=gpt-4o-mini
```

Restart the app after editing `.env`. The OpenAI API is billed separately from a ChatGPT subscription. `OPENAI_ORCHESTRATOR_MODEL` is optional — it's just for the routing step, so a cheaper/faster model there saves cost without affecting reply quality; it defaults to `OPENAI_MODEL` if left blank.

**An API key is required.** Every reply now goes through OpenAI — without a key, `bot.ai_enabled` is false and every message gets the same fixed reply: a short "having a technical issue, someone will reach out" message. There is no keyword-matching fallback mode anymore.

**Pricing guardrail:** the AI is only ever given the customer's own currency's pricing (inferred from their phone number's country code) — the other four currencies' rates are stripped out of what it sees entirely, not just told to ignore them. If a customer asks about pricing in a different country/currency, it can't leak real numbers because it was never given them, and it's instructed to say it only quotes in their own currency.

## 7a. Lead intake and staff notifications

Once a WhatsApp number signals it wants to enroll, the `intake` flow (`flows/intake_prompt.txt`) has a natural conversation collecting the parent's name, child's name, country, language preference, timezone, age, prior experience, availability, group preference, notes, referral source, and demo interest — in whatever order comes up naturally, skipping anything already mentioned. Answers are stored in `leads.json` (gitignored — it holds real names/ages/phone numbers).

Once every field is collected, the bot sends a WhatsApp summary to a staff number via the Meta Cloud API (the same API used for all outbound messages, see `notifications.py`), so Septi knows a lead is ready for him to follow up with — the bot itself never proposes a time, assigns a teacher/group, or confirms enrollment. Configure this in `.env`:

```env
WHATSAPP_TOKEN=your_meta_access_token
WHATSAPP_PHONE_NUMBER_ID=your_meta_phone_number_id
STAFF_NOTIFICATION_PHONE=+407XXXXXXXX
```

If these aren't set, the bot still works — it just skips sending the notification.

**Note:** WhatsApp's Business API restricts messages a business sends *first* (rather than as a reply) to either an active 24-hour conversation window or a pre-approved message template. If Septi hasn't recently messaged from this number himself, a proactive notification (or a nudge, see below) may not deliver until that's accounted for on the Meta side — this is a WhatsApp platform policy detail, not something this code can work around.

## 7b. Follow-up nudges

Three background jobs (`app.py`, via APScheduler) periodically check for leads that have gone quiet and send a short, model-generated check-in (`flows/nudge_prompt.txt`) via the Meta Cloud API: one for a lead stuck mid-intake for 24+ hours, one for a lead who finished intake but hasn't had a demo scheduled in 48+ hours, and one for a lead who said they wanted to think it over, 48+ hours later. Each only ever sends once per lead per reason.

## 8. Start the Flask app

```powershell
python app.py
```

Open this address in a browser:

```text
http://127.0.0.1:5000
```

You should see a small JSON status response.

## 9. Test the HTTP endpoint locally

Keep the Flask window running. Open a second PowerShell window, then run:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:5000/test-message `
  -ContentType "application/json" `
  -Body '{"message":"How long is the beginner class?","phone":"+14165550100"}'
```

## 10. Connect the Twilio WhatsApp Sandbox

1. Create or sign in to a Twilio account.
2. Open **Messaging → Try it out → Send a WhatsApp message**.
3. Activate the Sandbox.
4. From your phone, send Twilio's displayed `join ...` message to its Sandbox number.
5. Install ngrok and connect its authentication token.
6. While Flask is running on port 5000, start:

```powershell
ngrok http 5000
```

7. Copy the HTTPS forwarding address, for example:

```text
https://example.ngrok-free.app
```

8. In Twilio's Sandbox configuration, set **When a message comes in** to:

```text
https://example.ngrok-free.app/whatsapp
```

Use the **POST** method and save.

9. Send a WhatsApp message to the Sandbox number.

## 11. Turn on Twilio request validation

After the webhook works, edit `.env`:

```env
VALIDATE_TWILIO_SIGNATURE=true
TWILIO_AUTH_TOKEN=your_twilio_auth_token
PUBLIC_BASE_URL=https://example.ngrok-free.app
```

Restart Flask whenever the ngrok URL or `.env` changes. Free ngrok URLs may change each time ngrok is restarted, so both Twilio and `PUBLIC_BASE_URL` need the new address.

Do not deploy publicly with validation disabled.

## 12. Run the automated checks

```powershell
pytest
```

