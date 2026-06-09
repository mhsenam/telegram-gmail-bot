# Privacy Policy — TEMPLATE

> Google **requires** a public privacy policy (hosted on a domain you own) to verify an app
> that uses Gmail scopes, and it's good practice for any bot handling personal data. Fill in
> the bracketed parts, host it at a public URL (e.g. `https://yourdomain.com/privacy`), and
> link it in BotFather and on the Google OAuth consent screen. **This template is not legal
> advice** — have it reviewed if you're operating commercially.

---

## Privacy Policy for [Your Bot Name]

_Last updated: [DATE]_

### Who we are
[Your Bot Name] ("the Bot", "we") is a Telegram bot operated by [Your Name / Company],
contact: [email]. This policy explains what data we access, why, and your choices.

### What data we access
When you connect a Google account, you grant the Bot **read-only** access to your Gmail using
the `https://www.googleapis.com/auth/gmail.readonly` scope and your account's email address
(`userinfo.email`). Specifically, we:

- Read **message metadata** (sender, subject, date) and short previews **only to notify you**
  of new mail and to display your recent inbox on request.
- Read your Gmail **email address** to label the connected account.

We do **not** send, delete, or modify your email. We do not access your contacts, Drive, or
any other Google data.

### Google API Services User Data Policy
Our use and transfer of information received from Google APIs adheres to the
[Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy),
including the Limited Use requirements. We do not use Gmail data for advertising, do not sell
it, and do not allow humans to read it except as required for security, to comply with law, or
with your explicit consent.

### What we store
- Your Telegram user ID and basic preferences (e.g. notifications on/off).
- Your connected Google account's email address.
- OAuth tokens needed to check for new mail, **stored encrypted at rest**.
- A Gmail "history" cursor used to detect new messages.

We do **not** store the contents of your emails. Notification previews are sent to you in
Telegram and not retained by us beyond delivery.

### How we use it
Solely to provide the service: detecting new mail and notifying you, and showing your recent
inbox when you ask (`/inbox`).

### Sharing
We do not sell or share your data with third parties, except infrastructure providers
strictly necessary to run the service (e.g. our hosting/database provider) and as required by
law.

### Your choices and control
- **Disconnect anytime** with `/disconnect` (or `/accounts`) in the Bot. This **revokes** our
  access to your Google account and **deletes** your stored tokens immediately.
- You can also revoke access at any time at
  https://myaccount.google.com/permissions.
- To delete all your data, disconnect all accounts and message us at [email].

### Data retention
We retain account/connection data until you disconnect or request deletion, after which it is
removed promptly.

### Security
Tokens are encrypted at rest; access is read-only and least-privilege; secrets are not stored
in source code. No method is perfectly secure, but we take reasonable measures to protect your
data.

### Children
The Bot is not directed to children under [13/16, per your jurisdiction].

### Changes
We may update this policy; the "Last updated" date will change. Material changes will be
announced via the Bot.

### Contact
Questions or requests: [email].
