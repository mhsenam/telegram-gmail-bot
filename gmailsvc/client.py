"""Gmail API wrapper.

All functions here are SYNCHRONOUS (the official google-api-python-client is blocking).
Call them from async code with `asyncio.to_thread(...)` so they don't stall the event loop.
"""
from __future__ import annotations

from dataclasses import dataclass

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


@dataclass
class MessageMeta:
    id: str
    sender: str
    subject: str
    date: str
    snippet: str


def ensure_fresh(creds: Credentials) -> bool:
    """Refresh the access token if expired. Returns True if it was refreshed
    (so the caller can persist the updated credentials)."""
    if creds.valid:
        return False
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        return True
    return False


def _service(creds: Credentials):
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def get_profile(creds: Credentials) -> dict:
    """Returns {'emailAddress': ..., 'historyId': ..., ...}."""
    return _service(creds).users().getProfile(userId="me").execute()


def list_new_inbox_message_ids(
    creds: Credentials, start_history_id: str
) -> tuple[list[str], str | None, bool]:
    """List INBOX messages added since `start_history_id`.

    Returns (message_ids, latest_history_id, expired):
      - message_ids: newly-arrived INBOX message ids (de-duplicated, in order)
      - latest_history_id: the newest historyId to store for next time (or None)
      - expired: True if start_history_id is too old to use (caller must re-baseline)
    """
    svc = _service(creds)
    message_ids: list[str] = []
    seen: set[str] = set()
    latest_history_id: str | None = None
    page_token: str | None = None

    while True:
        try:
            resp = (
                svc.users()
                .history()
                .list(
                    userId="me",
                    startHistoryId=start_history_id,
                    historyTypes=["messageAdded"],
                    labelId="INBOX",
                    pageToken=page_token,
                )
                .execute()
            )
        except HttpError as exc:
            # 404 => the supplied historyId is older than Gmail keeps (~1 week).
            if exc.resp.status == 404:
                return [], None, True
            raise

        latest_history_id = resp.get("historyId", latest_history_id)
        for record in resp.get("history", []):
            for added in record.get("messagesAdded", []):
                msg = added.get("message", {})
                mid = msg.get("id")
                if not mid or mid in seen:
                    continue
                if "INBOX" in msg.get("labelIds", []):
                    seen.add(mid)
                    message_ids.append(mid)

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return message_ids, latest_history_id, False


def get_message_meta(creds: Credentials, message_id: str) -> MessageMeta:
    msg = (
        _service(creds)
        .users()
        .messages()
        .get(
            userId="me",
            id=message_id,
            format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        )
        .execute()
    )
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    return MessageMeta(
        id=message_id,
        sender=headers.get("from", "(unknown sender)"),
        subject=headers.get("subject", "(no subject)"),
        date=headers.get("date", ""),
        snippet=msg.get("snippet", ""),
    )


def list_recent_inbox(creds: Credentials, max_results: int = 5) -> list[MessageMeta]:
    """Latest INBOX messages, for the on-demand /inbox command."""
    svc = _service(creds)
    listing = (
        svc.users()
        .messages()
        .list(userId="me", labelIds=["INBOX"], maxResults=max_results)
        .execute()
    )
    out: list[MessageMeta] = []
    for ref in listing.get("messages", []):
        out.append(get_message_meta(creds, ref["id"]))
    return out
