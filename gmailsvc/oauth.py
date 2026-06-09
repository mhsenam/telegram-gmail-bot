"""Google OAuth 2.0 — building the consent URL, exchanging the code, revoking access.

We use the minimum scope needed to *read* an inbox preview: gmail.readonly. We also
request the user's email address so we can label the connected account. Each user
authorizes their OWN Google account; we store only the resulting tokens (encrypted).
"""
from __future__ import annotations

import json

import requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from config import settings

# Least-privilege: read-only access to Gmail + the account's email address.
# (gmail.readonly is a Google "restricted" scope — see SETUP.md about verification.)
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
_TOKEN_URI = "https://oauth2.googleapis.com/token"
_REVOKE_URI = "https://oauth2.googleapis.com/revoke"


def _client_config() -> dict:
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": _AUTH_URI,
            "token_uri": _TOKEN_URI,
            "redirect_uris": [settings.redirect_uri],
        }
    }


def build_auth_url(state: str) -> tuple[str, str | None]:
    """Build the Google consent URL for a `state` token.

    Returns (auth_url, code_verifier). The PKCE `code_verifier` must be stored and
    replayed in exchange_code(), because the consent step and the token exchange happen
    in two separate HTTP requests (and possibly two Flow objects).
    """
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, state=state)
    flow.redirect_uri = settings.redirect_uri
    auth_url, _ = flow.authorization_url(
        access_type="offline",        # we need a refresh token for background polling
        include_granted_scopes="true",
        prompt="consent",             # force a refresh token even on re-consent
    )
    return auth_url, flow.code_verifier


def exchange_code(code: str, code_verifier: str | None) -> Credentials:
    """Exchange the authorization `code` (with its PKCE `code_verifier`) for credentials.

    Blocking (network) — call via asyncio.to_thread from async code.
    """
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        code_verifier=code_verifier,
        autogenerate_code_verifier=False,
    )
    flow.redirect_uri = settings.redirect_uri
    flow.fetch_token(code=code)
    return flow.credentials


def credentials_to_json(creds: Credentials) -> str:
    return creds.to_json()


def credentials_from_json(data: str) -> Credentials:
    return Credentials.from_authorized_user_info(json.loads(data), SCOPES)


def revoke(creds: Credentials) -> None:
    """Tell Google to invalidate the token (best-effort). Blocking."""
    token = creds.refresh_token or creds.token
    if not token:
        return
    try:
        requests.post(
            _REVOKE_URI,
            params={"token": token},
            headers={"content-type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
    except requests.RequestException:
        # If revocation fails we still delete locally; user can remove access in their
        # Google account settings. We don't want disconnect to hard-fail on a network blip.
        pass
