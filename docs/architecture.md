# Architecture, scaling & upgrades

How the bot is built, how to make it truly real-time, how to scale it, and how to grow it
into a multi-service super app.

---

## Runtime model

`main.py` starts an asyncio event loop that hosts three cooperating pieces:

1. **Telegram bot** (`python-telegram-bot`, long polling) — receives `/connect`, `/inbox`,
   button taps, etc.
2. **Background poller** (`bot/notifier.py`, via PTB JobQueue) — every `POLL_INTERVAL_SECONDS`
   it sweeps all connected accounts and pushes new mail.
3. **OAuth web server** (`web/oauth_server.py`, aiohttp) — the one public HTTPS endpoint,
   `/oauth2callback`, where Google returns the user after consent.

The Gmail Python client is **synchronous**, so every Gmail call is wrapped in
`asyncio.to_thread(...)` to avoid blocking the loop.

### Data model (`storage/db.py`)

- `users(telegram_id, notifications_enabled, created_at)`
- `accounts(id, telegram_id, email, creds_enc, last_history_id, created_at)` — one row per
  connected Gmail; `creds_enc` is a Fernet-encrypted `Credentials.to_json()`;
  `last_history_id` is the Gmail sync cursor.
- `oauth_states(state, telegram_id, created_at)` — single-use CSRF tokens for in-flight OAuth.

### Why polling uses Gmail History

On connect we store the mailbox's current `historyId`. Each poll calls
`users.history.list(startHistoryId=…, historyTypes=[messageAdded], labelId=INBOX)`, which
returns only what changed since that cursor — cheap and exact. We advance the cursor each
round. If the cursor is older than Gmail retains (~1 week, returns 404), we re-baseline from
`getProfile` and skip that round (no backfill spam).

---

## Upgrade: TRUE push real-time (Gmail watch + Pub/Sub)

Polling gives ~30s latency. For instant delivery, Gmail can **push** a notification to a
Google Cloud **Pub/Sub** topic the moment mail arrives. Outline:

1. **Create a Pub/Sub topic** in your Google Cloud project, e.g. `gmail-push`.
2. Grant Gmail permission to publish to it: give
   `gmail-api-push@system.gserviceaccount.com` the **Pub/Sub Publisher** role on the topic.
3. **Create a push subscription** that POSTs to a new HTTPS endpoint on your server, e.g.
   `https://bot.yourdomain.com/pubsub`.
4. For each connected account, call **`users.watch`** with your topic name. Gmail then
   publishes `{emailAddress, historyId}` to the topic on every change. `watch` **expires
   after 7 days**, so re-call it on a schedule (a daily job).
5. Your `/pubsub` handler decodes the Pub/Sub message, looks up the account by
   `emailAddress`, and runs the *same* `list_new_inbox_message_ids` logic you already have —
   then notifies the user. (Verify the request is really from your subscription, e.g. via an
   OIDC token or a secret path.)

The current code is structured so this is an additive change: keep `last_history_id`, reuse
`gmailsvc/client.py`, and trigger the existing notify path from the webhook instead of (or in
addition to) the timer. Keep polling as a fallback for missed pushes.

> Trade-off: push removes latency and per-account polling cost, but adds Pub/Sub
> infrastructure, a second public endpoint, and 7-day `watch` renewal. Polling is the right
> default for launch; add push when latency or scale demands it.

---

## Scaling

| Concern | Start (now) | At scale |
|---------|-------------|----------|
| Database | SQLite file | **Postgres** (concurrent writers, backups) |
| Sessions / dedupe / rate counters | in DB | **Redis** |
| Update intake (Telegram) | long polling, 1 instance | webhooks + multiple stateless instances behind a load balancer |
| Mail delivery | 30s polling loop | **Pub/Sub push** (above) |
| Gmail API quota | fine for hundreds of users | batch metadata fetches; respect per-user limits; backoff on 429/5xx |
| Token encryption key | one `FERNET_KEY` | key rotation strategy (re-encrypt on a new key) |
| Secrets | `.env` | platform secret manager / KMS |

Notes:
- **Polling cost** grows linearly with connected accounts; each account is one `history.list`
  per interval. A few hundred accounts at 30s is fine. Thousands → move to Pub/Sub push and/or
  shard accounts across workers.
- The poller currently runs all accounts sequentially per sweep for simplicity. To parallelize,
  fan out with `asyncio.gather` over chunks (mind Gmail rate limits and Telegram's ~30 msg/s).
- Handle **`RefreshError` / `invalid_grant`** (already done): means the user revoked access →
  remove the account and tell them.

---

## Security checklist (already implemented + what to add)

Implemented here:
- ✅ Read-only Gmail scope (least privilege); can't send/delete mail.
- ✅ Tokens encrypted at rest (Fernet); key only in env.
- ✅ OAuth `state` CSRF token, single-use, per-user.
- ✅ Ownership checks on every disconnect callback.
- ✅ Token **revocation** on disconnect (Google revoke endpoint) + local delete.
- ✅ Baseline `historyId` on connect (no reading historical mail you didn't ask for).
- ✅ No tokens/PII in logs; friendly error pages.

Add before/at public launch:
- 🔲 HTTPS on the OAuth callback (required by Google) — see SETUP Part B.
- 🔲 Verify Pub/Sub requests if you add push (OIDC token / secret).
- 🔲 Rate-limit `/connect` per user to deter abuse.
- 🔲 Data retention & deletion policy; honor account deletion fully.
- 🔲 Google OAuth **verification + CASA** for the restricted Gmail scope (SETUP Part C).
- 🔲 Backups of the DB (it holds encrypted tokens) + a key-loss recovery plan.

---

## Adding more services (super-app growth)

The layout is deliberately service-oriented. To add, say, a Calendar service:

1. New package `calendarsvc/` mirroring `gmailsvc/` (its own OAuth scope set, client wrapper).
   You can reuse the same Google OAuth client; add the new scope and request incremental
   consent (`include_granted_scopes=true` is already set).
2. New handlers in `bot/handlers.py` (or a new `bot/calendar_handlers.py`) and register them
   in `main.py`.
3. Reuse `users` + the same encrypted-token pattern; add a `calendar_accounts` table or a
   generic `service` column on `accounts`.
4. If it needs background work, add another JobQueue job like `notifier.poll_all`.

Keep each service's scopes minimal and its tokens encrypted, and the "connect / manage /
disconnect" UX consistent with Gmail so users learn it once.
