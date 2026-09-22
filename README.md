# LeadMultiAgent — Telegram B2B lead monitor

**English** | [Русский](README.ru.md)

An autonomous system that watches Telegram group chats through a userbot, finds messages where people are looking for a product or service like yours, enriches the lead and sends **you** a notification with a draft reply. It never writes to anyone on its own: the draft only goes to you, and you decide whether to answer.

Bot messages and LLM prompts are in Russian.

## How it works

```
Telegram chats ──► userbot (Pyrogram) ──► keyword prefilter ──► Classifier ──► Enricher ──► Writer ──► notification bot ──► you
                                                                 score ≥ 0.7
```

| Agent | Model | What it does |
|---|---|---|
| Strategist | Groq `llama-3.1-8b-instant` | Turns your product description (`/start`) into an ideal customer profile, keywords, intent signals and anti-signals |
| Classifier | Groq `llama-3.1-8b-instant` | Decides whether a message is a lead; score 0–1, ≥ 0.7 means a clear lead |
| Enricher | NVIDIA NIM `llama-3.3-70b-instruct` | Summarizes who the author is |
| Writer | NVIDIA NIM `llama-3.3-70b-instruct` | Drafts a reply |
| Scout | Groq (categorization) | Finds and joins relevant chats — every Monday at 03:00 |
| Analyst | NVIDIA NIM `llama-3.3-70b-instruct` | Weekly digest — every Sunday at 10:00 |

Before any LLM call, a cheap prefilter scores the message: +2 per intent signal, +1 per keyword, −3 per anti-signal; messages below `KEYWORD_MIN_SCORE`, shorter than 20 characters or too old are skipped.

The notification has buttons "In progress" / "Not relevant" (lead status) and a link to the message.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env    # Windows: copy .env.example .env
```

Fill in `.env`:

| Variable | Where to get it |
|---|---|
| `TG_API_ID`, `TG_API_HASH` | your own app at [my.telegram.org](https://my.telegram.org) |
| `TG_PHONE` | the phone number of the account the userbot runs on |
| `BOT_TOKEN` | [@BotFather](https://t.me/BotFather) |
| `ADMIN_ID` | your numeric Telegram ID — notifications go there |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) |
| `NVIDIA_API_KEY` | [build.nvidia.com](https://build.nvidia.com) |
| `MAX_CHATS` | how many chats Scout may join (default 1000) |
| `KEYWORD_MIN_SCORE` | prefilter threshold (default 2) |

```bash
python main.py
```

On first run Pyrogram asks for the login code from Telegram; the session is saved to `session.session`. Then send `/start` to your bot and describe your product.

## Bot commands

- `/start` — first run, describe your product
- `/setup` — change the product (reruns Strategist and Scout)
- `/cancel` — cancel the product setup dialog
- `/stats` — statistics (chats, leads)
- `/leads` — the last 10 leads
- `/pause` / `/resume` — pause monitoring

## Chat list (optional)

If a `tgstat_chats.txt` file (one chat username per line) exists, Scout tries those chats first; otherwise it only uses Telegram search. `parse_tgstat.py` collects usernames from tgstat.ru with Playwright (`pip install playwright && playwright install chromium`), but tgstat.ru often blocks automated access. The list itself is not in the repository.

## Running on a server

- **Linux:** `leadmonitor.service` for systemd (fill in the user and paths), plus `check_heartbeat.sh` for cron — it restarts the service if `logs/heartbeat` is older than 5 minutes.
- **Windows:** `register_autostart.bat` registers `autostart.bat` as a task that starts with the system.

## Important

- **`session.session` gives full access to your Telegram account.** Never share or commit it — it is in `.gitignore`.
- `leads.db` and `logs/` contain messages and profiles of real people from the chats. That is personal data: keep it local.
- Joining hundreds of chats from one account can hit Telegram limits (`FLOOD_WAIT`) or get the account restricted. Scout pauses 10–20 seconds between joins and waits out `FLOOD_WAIT`, but a separate account is safer.
- Messages from archived chats do not arrive. Put monitored chats into a regular folder instead.
- NVIDIA NIM sometimes hangs, so every call has a 30-second timeout.
- `tgcrypto` is left out of the requirements because it needs C++ build tools; Pyrogram works without it, just with slower encryption.

## License

[MIT](LICENSE)
