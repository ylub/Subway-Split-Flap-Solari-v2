"""NJ TRANSIT token authentication and local cache handling."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import requests

from .models import Settings, TokenInfo
from .utils import read_json, write_json


TOKEN_TTL = timedelta(hours=23)


class NjtAuth:
    def __init__(self, settings: Settings, verbose: bool = True) -> None:
        self.settings = settings
        self.verbose = verbose

    def get_token(self, force_refresh: bool = False) -> str:
        cached = None if force_refresh else self._load_cached_token()
        if cached:
            self._log(f"Reusing cached NJ TRANSIT token from {self.settings.token_cache_path}.")
            return cached.token

        self._log("No reusable token found; requesting a new NJ TRANSIT token.")
        return self._request_new_token()

    def invalidate(self) -> None:
        if self.settings.token_cache_path.exists():
            self.settings.token_cache_path.unlink()
            self._log("Deleted cached NJ TRANSIT token after invalid-token response.")

    def _load_cached_token(self) -> TokenInfo | None:
        payload = read_json(self.settings.token_cache_path)
        if not payload:
            self._log("Token cache missing or unreadable.")
            return None
        token = str(payload.get("token") or "")
        obtained_at_raw = payload.get("obtained_at")
        if not token or not obtained_at_raw:
            self._log("Token cache has no token metadata.")
            return None
        try:
            obtained_at = datetime.fromisoformat(str(obtained_at_raw))
        except ValueError:
            self._log("Token cache timestamp is malformed.")
            return None
        if obtained_at.tzinfo is None:
            obtained_at = obtained_at.replace(tzinfo=UTC)
        age = datetime.now(UTC) - obtained_at.astimezone(UTC)
        if age >= TOKEN_TTL:
            self._log(f"Cached token is {age}; treating it as expired.")
            return None
        self._log(f"Cached token age is {age}; still within local {TOKEN_TTL} TTL.")
        return TokenInfo(token=token, obtained_at=obtained_at)

    def _request_new_token(self) -> str:
        url = f"{self.settings.api_base_url}/getToken"
        response = requests.post(
            url,
            headers={"accept": "text/plain"},
            files={
                "username": (None, self.settings.username),
                "password": (None, self.settings.password),
            },
            timeout=60,
        )
        response.raise_for_status()
        if not response.content:
            raise RuntimeError("NJ TRANSIT getToken returned an empty response.")

        payload = response.json()
        if payload is None:
            raise RuntimeError("NJ TRANSIT getToken returned null. Check credentials/account access.")
        if "errorMessage" in payload:
            raise RuntimeError(f"NJ TRANSIT getToken error: {payload['errorMessage']}")
        if str(payload.get("Authenticated", "")).lower() != "true":
            raise RuntimeError("NJ TRANSIT authentication failed.")
        token = str(payload.get("UserToken") or "")
        if not token:
            raise RuntimeError("NJ TRANSIT authentication did not return a token.")

        metadata = {
            "token": token,
            "obtained_at": datetime.now(UTC).isoformat(),
            "api_base_url": self.settings.api_base_url,
        }
        write_json(self.settings.token_cache_path, metadata)
        self._log(f"Saved new NJ TRANSIT token metadata to {self.settings.token_cache_path}.")
        return token

    def _log(self, message: str) -> None:
        if self.verbose:
            print(f"[auth] {message}")
