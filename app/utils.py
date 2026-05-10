"""Small utilities for configuration, files, and terminal output."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Iterable

from .models import Settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API_BASE_URL = "https://raildata.njtransit.com/api/GTFSRT"


def load_env(path: Path = PROJECT_ROOT / ".env") -> dict[str, str]:
    """Load simple KEY=VALUE pairs without requiring python-dotenv."""
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return {**values, **os.environ}


def load_settings(require_credentials: bool = True) -> Settings:
    env = load_env()
    username = env.get("NJT_USERNAME", "")
    password = env.get("NJT_PASSWORD", "")
    if require_credentials and (not username or not password):
        raise RuntimeError("Set NJT_USERNAME and NJT_PASSWORD in .env before calling NJ TRANSIT endpoints.")

    raw_dir = PROJECT_ROOT / env.get("NJT_RAW_DIR", "data/raw")
    archive_dir = PROJECT_ROOT / env.get("NJT_ARCHIVE_DIR", "data/archive")
    token_cache_path = PROJECT_ROOT / env.get("NJT_TOKEN_CACHE", "config/njt_token.json")
    gtfs_zip_path = raw_dir / "rail_gtfs.zip"
    return Settings(
        username=username,
        password=password,
        api_base_url=env.get("NJT_API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/"),
        raw_dir=raw_dir,
        archive_dir=archive_dir,
        token_cache_path=token_cache_path,
        gtfs_zip_path=gtfs_zip_path,
    )


def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_json_export(path: Path, rows: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, default=str) + "\n", encoding="utf-8")


def write_csv_export(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted({key for row in rows for key in row}))
        writer.writeheader()
        writer.writerows(rows)


def print_rows(rows: Iterable[dict[str, Any]], columns: list[str], limit: int | None = None) -> None:
    rows = list(rows)
    if limit is not None:
        rows = rows[:limit]
    if not rows:
        print("No rows.")
        return
    widths = {
        column: max(len(column), *(len(str(row.get(column, ""))) for row in rows))
        for column in columns
    }
    print("  ".join(column.ljust(widths[column]) for column in columns))
    print("  ".join("-" * widths[column] for column in columns))
    for row in rows:
        print("  ".join(str(row.get(column, "")).ljust(widths[column]) for column in columns))
