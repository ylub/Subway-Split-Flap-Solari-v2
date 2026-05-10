"""NJ TRANSIT rail GTFS/GTFS-RT HTTP client."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import requests

from .auth import NjtAuth
from .models import Settings
from .utils import ensure_dirs


ENDPOINT_FILES = {
    "getGTFS": "rail_gtfs.zip",
    "getAlerts": "alerts.pb",
    "getTripUpdates": "trip_updates.pb",
    "getVehiclePositions": "vehicle_positions.pb",
}


class NjtApiClient:
    def __init__(self, settings: Settings, verbose: bool = True) -> None:
        self.settings = settings
        self.auth = NjtAuth(settings, verbose=verbose)
        self.verbose = verbose

    def download_all(self, archive: bool = True) -> dict[str, Path]:
        return {
            endpoint: self.download(endpoint, archive=archive)
            for endpoint in ENDPOINT_FILES
        }

    def download(self, endpoint: str, archive: bool = True) -> Path:
        if endpoint not in ENDPOINT_FILES:
            raise ValueError(f"Unsupported endpoint {endpoint!r}.")
        ensure_dirs(self.settings.raw_dir, self.settings.archive_dir)
        target = self.settings.raw_dir / ENDPOINT_FILES[endpoint]
        content = self._post_with_token(endpoint)
        target.write_bytes(content)
        self._log(f"Saved {endpoint} to {target}.")
        if archive:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_path = self.settings.archive_dir / f"{target.stem}_{stamp}{target.suffix}"
            archive_path.write_bytes(content)
            self._log(f"Archived {endpoint} to {archive_path}.")
        return target

    def _post_with_token(self, endpoint: str) -> bytes:
        token = self.auth.get_token()
        content = self._post(endpoint, token)
        if self._is_invalid_token_response(content):
            self._log("API returned Invalid token; requesting one replacement token and retrying.")
            self.auth.invalidate()
            token = self.auth.get_token(force_refresh=True)
            content = self._post(endpoint, token)
        if self._is_invalid_token_response(content):
            raise RuntimeError(f"NJ TRANSIT {endpoint} returned Invalid token after refresh.")
        if self._is_json_error(content):
            raise RuntimeError(f"NJ TRANSIT {endpoint} error: {content.decode('utf-8', errors='replace')}")
        if not content:
            raise RuntimeError(f"NJ TRANSIT {endpoint} returned an empty response.")
        return content

    def _post(self, endpoint: str, token: str) -> bytes:
        url = f"{self.settings.api_base_url}/{endpoint}"
        response = requests.post(
            url,
            headers={"accept": "*/*"},
            files={"token": (None, token)},
            timeout=90,
        )
        response.raise_for_status()
        return response.content

    @staticmethod
    def _is_invalid_token_response(content: bytes) -> bool:
        text = content[:500].decode("utf-8", errors="ignore")
        return "Invalid token" in text

    @staticmethod
    def _is_json_error(content: bytes) -> bool:
        text = content[:200].lstrip().decode("utf-8", errors="ignore")
        return text.startswith("{") and "errorMessage" in text

    def _log(self, message: str) -> None:
        if self.verbose:
            print(f"[api] {message}")
