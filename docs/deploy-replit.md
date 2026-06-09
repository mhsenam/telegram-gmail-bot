# Deploying on Replit

This bot is **always-on** (long polling to Telegram + a 30-second mail poller) **and** runs a
small web server (the OAuth callback). That combination decides everything below.

> Two things bite people on Replit. Read **#0** and **#3** before you start.

---

## 0. Pick the right deployment type: **Reserved VM** (not Autoscale)

| Type | Behavior | Good for this bot? |
|------|----------|--------------------|
| **Reserved VM** | Runs continuously, fixed monthly price (~$6+/mo) | ✅ **Yes — use this** |
| Autoscale | Request-driven, **scales to zero when idle** | ❌ No — it would stop polling and you'd miss notifications |
| Static | No server | ❌ No |

Our bot keeps a persistent process (polling + background job), so it must stay running.
Replit removed the old "Always On" toggle — **Reserved VM is the way** to keep a bot alive.

---

## 1. Get the code onto Replit

Either:
- **Import from GitHub** (push this repo first, then Replit → Create → Import from GitHub), or
- **Upload** the `gmail-super-bot` folder into a new Python Repl.

Replit auto-detects Python and installs `requirements.txt`.

---

## 2. Set Secrets (environment variables)

Open the **Secrets** tab (🔒) and add each key — do **NOT** upload your `.env`:

| Secret | Value |
|--------|-------|
| `TELEGRAM_BOT_TOKEN` | from @BotFather |
| `GOOGLE_CLIENT_ID` | Google Cloud OAuth client |
| `GOOGLE_CLIENT_SECRET` | same |
| `FERNET_KEY` | your existing key (keep it **stable** forever) |
| `OAUTH_REDIRECT_BASE_URL` | set in step 4 (your Replit URL) |
| `DATABASE_URL` | auto-set when you add Replit PostgreSQL (see step 3) |
| `POLL_INTERVAL_SECONDS` | optional, e.g. `30` |

Notes:
- **No proxy needed.** Replit's servers can reach `api.telegram.org` directly — leave
  `TELEGRAM_PROXY` unset (the VPN/proxy you used locally is irrelevant here).
- Secrets are injected as real env vars; the app reads them automatically (no `.env` file).

---

## 3. ✅ Database: use PostgreSQL (survives redeploys)

On Replit Deployments, local-file writes (the SQLite `gmail_bot.db`) are **wiped on every
redeploy** — which would force all users to reconnect after each update. The bot now supports
**PostgreSQL** out of the box, which persists. **Do this for any real deployment:**

1. In Replit, open **Tools → PostgreSQL** (or the Database pane) and **create a database**.
   Replit provisions one and sets the **`DATABASE_URL`** environment variable automatically.
2. That's it — the app auto-detects `DATABASE_URL` and uses Postgres instead of SQLite. No
   code change needed. (Locally, with `DATABASE_URL` unset, it still uses SQLite.)
3. Confirm in the logs on startup: you'll see `Storage backend: PostgreSQL`.

> How it works: `storage/db.py` selects the backend at startup — `_postgres.py` (asyncpg) when
> `DATABASE_URL` is present, else `_sqlite.py`. Same API, so nothing else changes. `asyncpg`
> is already in `requirements.txt`.

If `DATABASE_URL` isn't auto-set, copy the connection string from the Postgres pane into a
Secret named `DATABASE_URL` (format `postgresql://user:pass@host:5432/dbname`).

---

## 4. Deploy (Reserved VM) and get your public URL

1. **Tools → Deployments → Reserved VM**.
2. Run command: `python main.py` (the included `.replit` already sets this).
3. Deploy. Replit gives you a URL like:
   ```
   https://your-bot-name.your-username.replit.app
   ```
4. Copy that URL.

---

## 5. Wire up the OAuth redirect (critical)

The Google sign-in must come back to your Replit URL, not localhost:

1. Set the Secret:
   ```
   OAUTH_REDIRECT_BASE_URL = https://your-bot-name.your-username.replit.app
   ```
2. In **Google Cloud Console → APIs & Services → Credentials → your OAuth client →
   Authorized redirect URIs**, add:
   ```
   https://your-bot-name.your-username.replit.app/oauth2callback
   ```
   (Keep your `http://localhost:8080/oauth2callback` too, so local dev still works.)
3. **Redeploy** so the new `OAUTH_REDIRECT_BASE_URL` takes effect.

---

## 6. Ports (already handled)

- The OAuth web server binds `0.0.0.0:8080`; the included `.replit` maps it to the public
  port. The app also honors a platform `$PORT` if Replit injects one — no action needed.
- The bot talks to Telegram via **outbound** long polling, so it needs no inbound port for
  Telegram. The only public endpoint is `/oauth2callback`.

---

## 7. Test it

1. Open your bot in Telegram → `/start` → `/connect`.
2. Approve on Google → you should land on "Gmail connected 🎉" (now served from your Replit
   URL) and get a confirmation DM.
3. Send yourself an email → notification within ~30s. Try `/inbox`.

---

## 8. Operating it

- **Logs:** the Deployments pane shows live logs (you'll see the `poll_all` ticks).
- **Updating code:** push/redeploy. ⚠️ Remember the SQLite caveat (#3) until you move to
  Postgres.
- **Cost:** Reserved VM is a fixed monthly fee regardless of traffic — fine for an always-on
  bot. Pick the smallest tier to start; this bot is light.
- **Secrets stay put** across deploys, so `FERNET_KEY` remains stable (don't change it, or
  stored tokens become undecryptable).

---

## TL;DR

1. Reserved VM (not Autoscale).
2. Put secrets in the Secrets tab (no `.env`).
3. Add Replit **PostgreSQL** (sets `DATABASE_URL`) so data survives redeploys.
4. Deploy → copy the `.replit.app` URL → set `OAUTH_REDIRECT_BASE_URL` to it + add
   `<url>/oauth2callback` to Google → redeploy.
