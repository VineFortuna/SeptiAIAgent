---
name: verify-sep7ro-bot
description: Runs the automated test suite plus a quick live sanity-check conversation against the Sep7Ro WhatsApp bot to confirm it still works after changes. Use when the user asks to verify, test, check, or make sure the bot still works.
---

# Verify the Sep7Ro WhatsApp bot

Run this whenever the user asks to verify/test/check the bot, or right after making
non-trivial changes to `bot.py`, `app.py`, `company_data.json`, or `notifications.py`.

## 1. Run the automated test suite

```bash
cd <project root>
python -m pytest -q
```

Report the pass/fail count. If anything fails, read the failure output and fix the
underlying issue before continuing — don't just report "tests failed" and stop.

## 2. Run a live sanity-check conversation

Use an **isolated temp `leads_path`** for every check below — never instantiate
`ClassAssistant()` with no arguments for this, it would write test data into the real
`leads.json`. Pattern:

```python
from bot import ClassAssistant
from pathlib import Path
import tempfile

tmp = Path(tempfile.mktemp(suffix=".json"))
bot = ClassAssistant(leads_path=tmp)
```

Check each of these and confirm the reply looks right (sounds like Septi, no
"Label: value" patterns, no em dashes, no trailing periods on short replies):

1. **English greeting** on a fresh number (e.g. `+14165559001`): send `"Hi"`,
   confirm a casual first-person reply, not a repeated double-greeting.
2. **Romanian greeting** on a different fresh number: send `"Salut"`, confirm the
   reply is actually in Romanian (not English).
3. **Fresh-number intake start**: confirm the reply ends with `?` (it's asking the
   first of the 6 intake questions).
4. **Known booking lookup**: on `+14165550100` (has a sample booking in
   `bookings.json`), send `"What time is my class?"`, confirm it returns the sample
   time and skips intake entirely.
5. **Pricing question** — only if `OPENAI_API_KEY` is set in `.env` (check
   `bot.ai_enabled`); if not set, skip this check and say so in the summary rather
   than treating it as a failure. If set, ask `"How much does the standard package
   cost?"` on a UK number (e.g. `+447911123456`) and confirm it mentions `£`/`GBP`
   rather than falling back to a handoff message.

## 3. Report back

Give a concise summary: test pass/fail count, which sanity checks passed, which
were skipped (and why, e.g. no API key configured), and anything that looks off
compared to expected behavior. Don't dump full conversation transcripts unless
something failed and the detail is needed to explain why.

Never leave temp files behind, and never touch the real `leads.json` or
`pending_messages.json` while running these checks.
