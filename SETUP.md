# SETUP — what YOU need to do

I wrote all the code. To run it, you must create a few accounts/keys (I can't do these for
you — they require logging into your Telegram and Google accounts). Follow this in order.
Budget ~30 minutes for first-time setup.

> 🔴 **Read [Part C: Publishing worldwide](#part-c--publishing-to-the-whole-world-important)
> before you promise this to users.** Gmail access is a Google "restricted" scope and Google
> gates worldwide use behind an app-verification + security review. This is the one thing that
> can't be skipped, so know it up front.

---

## Part A — Get it running locally (test mode)

### 1. Install Python
Python **3.10+**. Check: `python --version`.

### 2. Create the Telegram bot
1. In Telegram, message **@BotFather** → `/newbot` → pick a name and a username ending in `bot`.
2. Copy the **token** (`123456789:AA...`). → this is `TELEGRAM_BOT_TOKEN`.

### 3. Create a Google Cloud project + enable the Gmail API
1. Go to https://console.cloud.google.com/ → create a project (top bar → New Project).
2. **APIs & Services → Library** → search **Gmail API** → **Enable**.

### 4. Configure the OAuth consent screen
1. **APIs & Services → OAuth consent screen**.
2. **User type: External** → Create.
3. Fill app name, your support email, developer email. (Logo/links optional for testing.)
4. **Scopes** → Add → search and add **`.../auth/gmail.readonly`** and
   **`.../auth/userinfo.email`** → Update → Save.
5. **Test users** → add the Google account(s) you'll test with (your own Gmail).
   👉 While the app is in *Testing*, only these listed accounts can connect (max 100).
6. Save. Leave **Publishing status = Testing** for now.

### 5. Create the OAuth client credentials
1. **APIs & Services → Credentials → Create credentials → OAuth client ID**.
2. **Application type: Web application**.
3. Under **Authorized redirect URIs**, add exactly:
   ```
   http://localhost:8080/oauth2callback
   ```
   (Must match `OAUTH_REDIRECT_BASE_URL` + `/oauth2callback`. Change the port only if you also
   change it in `.env`.)
4. Create → copy the **Client ID** and **Client secret** → `GOOGLE_CLIENT_ID` /
   `GOOGLE_CLIENT_SECRET`.

### 6. Generate the token-encryption key
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Copy the output → `FERNET_KEY`. **Keep it stable** — changing it makes all stored
connections undecryptable (users would need to reconnect).

### 7. Configure `.env`
```bash
# from the gmail-super-bot folder
copy .env.example .env      # Windows  (cp on macOS/Linux)
```
Open `.env` and paste your 4 secrets: `TELEGRAM_BOT_TOKEN`, `GOOGLE_CLIENT_ID`,
`GOOGLE_CLIENT_SECRET`, `FERNET_KEY`. Leave the rest as-is for local testing.

### 8. Install dependencies
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1          # PowerShell (Windows)
# source .venv/bin/activate          # macOS/Linux
pip install -r requirements.txt
```

### 9. Run it
```bash
python main.py
```
You should see "OAuth callback server listening…" and "Bot is running."

### 10. Try it
In Telegram: open your bot → `/start` → `/connect` → tap **Connect Gmail** → sign in with a
**test user** account → approve. You'll be bounced back with "✅ Connected". Send yourself an
email and watch it appear within ~30 seconds. Try `/inbox`, `/accounts`, `/settings`,
`/privacy`, and disconnecting.

> On the consent screen you'll see an **"unverified app"** warning while in Testing — that's
> expected. Click *Advanced → go to (app)* to proceed as a test user.

---

## Part B — Deploy to a server (so it runs 24/7 with a real URL)

Local works, but Google needs a **public HTTPS** redirect for real users, and the bot must
run continuously.

1. **Get a host** with a public IP/domain: a small VPS (Hetzner, DigitalOcean, etc.), or a
   PaaS (Railway, Render, Fly.io). You need a **domain with HTTPS** (Let's Encrypt via
   Caddy/nginx, or the platform's built-in TLS).
2. Point a domain at it, e.g. `https://bot.yourdomain.com`. Make sure the OAuth web server
   (port 8080 by default) is reachable behind TLS at `/oauth2callback`. Typically you put a
   reverse proxy (Caddy/nginx) in front that terminates HTTPS and forwards to `127.0.0.1:8080`.
3. In `.env` set:
   ```
   OAUTH_REDIRECT_BASE_URL=https://bot.yourdomain.com
   ```
4. In **Google Cloud → Credentials → your OAuth client → Authorized redirect URIs**, add:
   ```
   https://bot.yourdomain.com/oauth2callback
   ```
5. Run it as a managed process so it restarts on crash/reboot:
   - **systemd** unit, or **pm2**, or **Docker** with `restart: unless-stopped`, or your
     PaaS's "always-on worker".
6. Keep the `.env` / secrets in the platform's secret manager — never commit them.

> The bot itself uses **long polling** to talk to Telegram, so it needs no inbound port for
> Telegram. The only public endpoint you expose is the **OAuth callback** (`/oauth2callback`).

---

## Part C — Publishing to the whole world (IMPORTANT)

You said this will be "published around the world." For Gmail, that has a hard requirement
you must plan for:

### Gmail scopes are *restricted* — Google verification is required
`gmail.readonly` is one of Google's **restricted scopes**. To let **anyone** (beyond your 100
test users) connect their Gmail, Google requires your OAuth app to pass:

1. **OAuth app verification** — brand verification, accurate consent screen, a **privacy
   policy URL** and homepage on a domain you own, and a YouTube demo video of the OAuth flow.
2. **A security assessment (CASA)** for restricted scopes — an annual third-party assessment.
   It can take weeks and may incur cost. This is Google's requirement for apps that read user
   email at scale.

Until you complete verification:
- The app stays in **Testing** (≤100 explicitly-added test users), **or**
- In **Production/unverified**, users see a scary "Google hasn't verified this app" warning
  and restricted scopes are blocked for non-test users.

**What this means for you:**
- ✅ You can build, demo, and onboard up to 100 testers right now with zero verification.
- ⏳ For a true public launch, start Google's verification early (it's the long pole).
- 💡 Privacy-lighter alternative: if you only need **sender + subject** (no body preview),
  the **`gmail.metadata`** scope is *also* restricted but some review paths are lighter. This
  bot uses `gmail.readonly` to show snippets; switching to metadata is a one-line scope change
  in `gmailsvc/oauth.py` (you'd drop the snippet preview).

Start here: https://support.google.com/cloud/answer/9110914 (OAuth verification) and the
"restricted scopes" section of the Google API Services User Data Policy.

### Other must-haves before a public launch
- **Privacy policy** hosted on your domain — a ready template is in
  [docs/privacy-policy-template.md](docs/privacy-policy-template.md). Link it in BotFather
  (`/setprivacy` text or description) and in the Google consent screen.
- **Terms of service** (recommended).
- Set bot **description/about/commands** in BotFather so it looks finished.
- Pick a **database**: SQLite is fine to start; for many users move to Postgres + Redis (see
  [docs/architecture.md](docs/architecture.md)).
- Decide on **true push real-time** (Gmail `watch()` + Pub/Sub) vs the current 30s polling —
  see [docs/architecture.md](docs/architecture.md). Polling is perfectly fine for launch.

---

## Quick reference: the 4 secrets you must provide

| `.env` key | Where it comes from |
|---|---|
| `TELEGRAM_BOT_TOKEN` | @BotFather → `/newbot` |
| `GOOGLE_CLIENT_ID` | Google Cloud → Credentials → OAuth client (Web) |
| `GOOGLE_CLIENT_SECRET` | same OAuth client |
| `FERNET_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

Everything else has a sensible default. Got these four + the redirect URI registered? It runs.
