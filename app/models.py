"""Shared data models for NJ TRANSIT GTFS and GTFS-RT data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Settings:
    username: str
    password: str
    api_base_url: str
    raw_dir: Path
    archive_dir: Path
    token_cache_path: Path
    gtfs_zip_path: Path


@dataclass(frozen=True)
class TokenInfo:
    token: str
    obtained_at: datetime
    source: str = "cache"


@dataclass(frozen=True)
class Station:
    stop_id: str
    stop_name: str
    stop_lat: float | None = None
    stop_lon: float | None = None
    parent_station: str = ""


@dataclass(frozen=True)
class Route:
    route_id: str
    route_short_name: str
    route_long_name: str
    route_color: str = ""
    route_text_color: str = ""


@dataclass(frozen=True)
class Trip:
    trip_id: str
    route_id: str
    service_id: str
    trip_headsign: str = ""
    direction_id: str = ""


@dataclass(frozen=True)
class StopTime:
    trip_id: str
    stop_id: str
    arrival_time: str
    departure_time: str
    stop_sequence: int


@dataclass(frozen=True)
class AlertEntity:
    id: str
    active_periods: list[dict[str, int | None]]
    informed_entities: list[dict[str, str]]
    cause: str
    effect: str
    header: str
    description: str
    url: str


@dataclass(frozen=True)
class TripUpdateEntity:
    id: str
    trip_id: str
    route_id: str
    start_time: str
    start_date: str
    schedule_relationship: str
    vehicle_id: str
    stop_time_updates: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class VehiclePositionEntity:
    id: str
    trip_id: str
    route_id: str
    start_time: str
    start_date: str
    vehicle_id: str
    label: str
    current_stop_sequence: int | None
    stop_id: str
    current_status: str
    timestamp: int | None
    latitude: float | None
    longitude: float | None
    bearing: float | None
    speed: float | None

