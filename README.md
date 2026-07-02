# Sep7Ro WhatsApp Assistant

This project receives WhatsApp messages through Twilio and responds as Septi, the founder of Sep7Ro chess school, with:

- approved class information from `company_data.json`, bilingual (Romanian/English)
- a 6-question lead-intake conversation for new contacts, with a WhatsApp notification to staff when it completes
- a class registration link
- a personal booking lookup from `bookings.json`
- a safe handoff when it cannot confirm an answer
- optional OpenAI-based natural-language answers for pricing, discounts, lichess onboarding, and tournaments

Replies are written in first person as Septi (no disclosure that it's automated, by explicit request), and most replies are picked from a pool of phrasings that never repeats the same wording twice in a row, so it doesn't read like a templated bot. See `bot.py`'s `_pick`/`_pick_no_repeat`/`_value` for how that works.

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
What time is my class?
Can I talk to a staff member?

Unde sunteti?
Are nevoie de experienta?
Ce clase aveti?
```

The sample phone number `+14165550100` has a fake booking in `bookings.json` and skips the lead-intake flow. Use any other number (e.g. `+40733445566`) to see the 6-question intake conversation a new contact gets.

## 6. Add company information

Open `company_data.json`. Most facts are lists of phrasing variants under `"en"`/`"ro"` keys (e.g. `"location": {"en": [...], "ro": [...]}`) — the bot picks a different one each time it's asked, in whichever language the customer is writing. A handful of fields are still single placeholder strings starting with `REPLACE` because that information hasn't been provided yet: `registration_link`, `contact_phone`, `contact_email`, `payment_methods`, `late_arrival_policy`, `private_lessons`, `waitlist_policy`. Fill those in with real values once available — until then, the bot correctly says it'll check and get back to you rather than guessing.

Do not enter customer passwords, payment details, medical information, or other unnecessary sensitive information.

## 7. Add OpenAI

Create an OpenAI API key and place it in `.env`:

```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-5.5
```

Restart the app after editing `.env`. The OpenAI API is billed separately from a ChatGPT subscription.

Without an API key, the bot still covers a lot — greetings, thanks, staff-handoff requests, help, the lead-intake conversation, and most FAQ facts (location, hours, schedule, what to bring/wear, age/experience requirements, group size, cancellation/rescheduling policy, class duration, registration, and booking lookup) in both English and Romanian, all via keyword matching with no AI involved. Pricing, discounts, the lichess.org onboarding steps, and tournament info specifically require the API key, since that content only exists in the AI-routed knowledge base, not as hardcoded rules. Any phrasing that doesn't match a known keyword also falls back to the AI (or the handoff message if no key is set).

**Pricing guardrail:** the AI is only ever given the customer's own currency's pricing (inferred from their phone number's country code) — the other three currencies' rates are stripped out of what it sees entirely, not just told to ignore them. If a customer asks about pricing in a different country/currency, it can't leak real numbers because it was never given them, and it's instructed to say it only quotes in their own currency.

## 7a. Lead intake and staff notifications

Any WhatsApp number that isn't already in `bookings.json` is treated as a new lead. The bot asks 6 quick qualifying questions (child's class language, time zone, child's age, prior chess experience, weekday/weekend availability, group preference), storing answers in `leads.json` (gitignored — it holds real names/ages/phone numbers, unlike the placeholder `bookings.json`). FAQ questions asked mid-intake (e.g. "how much does it cost?") are still answered — they don't get captured as intake answers.

Once all 6 fields are collected, the bot sends a WhatsApp summary to a staff number via the Twilio REST API, so Septi knows a lead is ready for him to follow up with — the bot itself never proposes a time, assigns a teacher/group, or confirms enrollment. Configure this in `.env`:

```env
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
STAFF_NOTIFICATION_PHONE=whatsapp:+407XXXXXXXX
```

If these aren't set, the bot still works — it just skips sending the notification.

**Note:** WhatsApp's Business API restricts messages a business sends *first* (rather than as a reply) to either an active 24-hour conversation window or a pre-approved message template. If Septi hasn't recently messaged the Twilio number himself, this notification may not deliver until that's set up on the Twilio side — this is a Twilio/WhatsApp policy detail, not something this code can work around.

## 7b. Business hours (7am-9pm Eastern)

The bot only replies live between 7am and 9pm Eastern time (auto-adjusts for EST/EDT — see `is_within_business_hours()` in `bot.py`). A message that arrives outside that window gets queued in `pending_messages.json` (gitignored, holds real message content) and gets **no immediate reply at all**, by design.

A background job (`app.py`, using APScheduler) checks every 10 minutes whether business hours have resumed, and once they have, answers each queued message through the normal `reply()` pipeline and sends it via the Twilio REST API — so a message sent at 11pm gets a real reply once 7am hits, not silence. If a send fails (e.g. Twilio hiccup), the message stays queued and retries on the next check rather than being dropped.

This only applies to the real `/whatsapp` webhook — `chat_demo.py` and `/test-message` ignore business hours entirely, so local testing/development works at any hour.

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

## What still needs to be connected later

`bookings.json` is only a starter demonstration. For real customer schedules, it should be replaced with the company's actual booking system, calendar, spreadsheet, or database. The bot must never guess a personal class time.
