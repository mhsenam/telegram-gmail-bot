# 📬 Gmail Super Bot

A Telegram bot designed as a **multi-service "super app."** The first service is a
**real-time Gmail inbox**: every connected user gets a Telegram notification the moment new
mail arrives in their own Gmail account(s). Built multi-user and privacy-first so it can be
published publicly.

> 👉 **To actually run it, follow [SETUP.md](SETUP.md).** That's the "what you need to do"
> guide. This file explains what it is and how it works.

---

## What it does

- **Connect your own Gmail** via Google OAuth (`/connect`) — each Telegram user links their
  own account(s). No shared credentials.
- **Real-time notifications** — new INBOX mail is pushed to your Telegram chat (sender,
  subject, preview) within seconds (default 30s polling).
- **Multiple accounts per user** — connect several Gmail addresses.
- **On-demand inbox** (`/inbox`) — see your latest emails right now.
- **Full self-service management** — `/accounts` to list, one-tap **disconnect** (which
  *revokes* Google access and deletes tokens), `/settings` to toggle notifications.
- **Privacy-first** — read-only Gmail scope, tokens **encrypted at rest**, clear `/privacy`.

## Commands

| Command | Action |
|---------|--------|
| `/start`, `/help` | Welcome + menu |
| `/connect` | Link a Gmail account (OAuth) |
| `/inbox` | Show latest emails now |
| `/accounts` | List / disconnect connected accounts |
| `/settings` | Notifications on/off |
| `/privacy` | What data the bot accesses |
| `/about` | About |

## How it works (architecture at a glance)

```
 Telegram user ──/connect──► Bot ──builds OAuth URL──► Google consent screen
       ▲                                                      │ user approves
       │                                                      ▼
       │                         Google ──redirect w/ code──► web/oauth_server.py
       │                                                      │ exchange code → tokens
       │                                                      ▼
       │                                   storage (SQLite): tokens ENCRYPTED (Fernet)
       │                                                      │
   notifications                          bot/notifier.py (every 30s, JobQueue)
       │                                   for each account: Gmail history.list → new mail
       └───────────────────── "📧 New email …" ◄──────────────┘
```

- **`main.py`** runs three things on one event loop: the Telegram bot (long polling), the
  background mail poller (`bot/notifier.py`), and the OAuth callback web server
  (`web/oauth_server.py`).
- **OAuth `state`** ties each consent flow to the requesting Telegram user (CSRF-safe) and is
  single-use.
- **On connect** we record the account's current Gmail `historyId` as a baseline, so you're
  only notified about mail that arrives *after* connecting — never your whole backlog.
- **Tokens** are stored only as Fernet-encrypted blobs; the key lives in `FERNET_KEY` (env),
  never in the DB.

## Project layout

```
gmail-super-bot/
├── main.py                  # entry point: bot + poller + web server on one loop
├── config.py                # env-based settings
├── requirements.txt
├── .env.example             # copy to .env and fill in (see SETUP.md)
├── SETUP.md                 # ← what YOU must do to run/publish it
├── bot/
│   ├── handlers.py          # commands + inline-button (callback) router
│   ├── keyboards.py         # inline keyboards
│   └── notifier.py          # background job: poll inboxes → push new mail
├── gmailsvc/
│   ├── oauth.py             # OAuth URL / code exchange / revoke
│   └── client.py            # Gmail API: profile, history, message metadata
├── storage/
│   ├── db.py                # SQLite (users, accounts, oauth_states)
│   └── crypto.py            # Fernet encryption of tokens
├── web/
│   └── oauth_server.py      # aiohttp OAuth redirect handler
└── docs/
    ├── architecture.md          # real-time (Pub/Sub) upgrade, scaling, adding services
    └── privacy-policy-template.md
```

## Adding the next service (it's built for this)

This is structured as a "super app." To add a second service (calendar, weather, reminders,
news…), add a new package alongside `gmailsvc/`, register its commands in `main.py`, and reuse
the same user table. See [docs/architecture.md](docs/architecture.md) → "Adding more services."

## Status & limits to know

- **Real-time = ~30s polling** by default (works on any host). True push (Gmail `watch()` +
  Pub/Sub) is documented in [docs/architecture.md](docs/architecture.md).
- **Public launch requires Google verification** of the Gmail scope (restricted scope). You
  can run with up to 100 test users immediately; see [SETUP.md › Part C](SETUP.md#part-c--publishing-to-the-whole-world-important).
- **SQLite** is fine to start; swap to Postgres/Redis for scale.

## License / reuse

This is your project scaffold — adapt freely. Keep the security properties (encrypted tokens,
read-only scope, revoke-on-disconnect, no secrets in code) intact when you extend it.
