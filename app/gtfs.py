"""Static GTFS ZIP reader and lookup helpers."""

from __future__ import annotations

import csv
import io
import zipfile
from collections import defaultdict
from pathlib import Path

from .models import Route, Station, StopTime, Trip


class StaticGtfs:
    def __init__(self, zip_path: Path | None = None, extracted_dir: Path | None = None) -> None:
        self.zip_path = zip_path
        self.extracted_dir = extracted_dir
        self.stops = self._load_table("stops.txt")
        self.routes = self._load_table("routes.txt")
        self.trips = self._load_table("trips.txt")
        self.stop_times = self._load_table("stop_times.txt")
        self.shapes = self._load_table("shapes.txt")
        self.calendar = self._load_table("calendar.txt")
        self.calendar_dates = self._load_table("calendar_dates.txt")
        self._stops_by_id = {row["stop_id"]: row for row in self.stops}
        self._routes_by_id = {row["route_id"]: row for row in self.routes}
        self._trips_by_id = {row["trip_id"]: row for row in self.trips}
        self._stop_times_by_trip: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in self.stop_times:
            self._stop_times_by_trip[row["trip_id"]].append(row)
        for rows in self._stop_times_by_trip.values():
            rows.sort(key=lambda row: int(row.get("stop_sequence") or 0))

    @classmethod
    def from_default_sources(cls, zip_path: Path) -> "StaticGtfs":
        if zip_path.exists():
            return cls(zip_path=zip_path)
        fallback = Path("gtfs/njt/rail_data")
        if fallback.exists():
            return cls(extracted_dir=fallback)
        raise FileNotFoundError(f"No GTFS ZIP at {zip_path}; run `python app.py download` first.")

    def stations(self, query: str = "") -> list[Station]:
        needle = query.lower()
        rows = [
            row for row in self.stops
            if not needle or needle in row.get("stop_name", "").lower() or needle in row.get("stop_id", "").lower()
        ]
        return [
            Station(
                stop_id=row["stop_id"],
                stop_name=row.get("stop_name", ""),
                stop_lat=_float_or_none(row.get("stop_lat")),
                stop_lon=_float_or_none(row.get("stop_lon")),
                parent_station=row.get("parent_station", ""),
            )
            for row in sorted(rows, key=lambda item: item.get("stop_name", ""))
        ]

    def route_list(self, query: str = "") -> list[Route]:
        needle = query.lower()
        rows = [
            row for row in self.routes
            if not needle
            or needle in row.get("route_id", "").lower()
            or needle in row.get("route_short_name", "").lower()
            or needle in row.get("route_long_name", "").lower()
        ]
        return [
            Route(
                route_id=row["route_id"],
                route_short_name=row.get("route_short_name", ""),
                route_long_name=row.get("route_long_name", ""),
                route_color=row.get("route_color", ""),
                route_text_color=row.get("route_text_color", ""),
            )
            for row in sorted(rows, key=lambda item: (item.get("route_short_name", ""), item.get("route_long_name", "")))
        ]

    def lookup_trip(self, trip_id: str) -> Trip | None:
        row = self._trips_by_id.get(trip_id)
        if not row:
            return None
        return Trip(
            trip_id=row["trip_id"],
            route_id=row.get("route_id", ""),
            service_id=row.get("service_id", ""),
            trip_headsign=row.get("trip_headsign", ""),
            direction_id=row.get("direction_id", ""),
        )

    def lookup_route(self, route_id: str) -> Route | None:
        row = self._routes_by_id.get(route_id)
        if not row:
            return None
        return Route(
            route_id=row["route_id"],
            route_short_name=row.get("route_short_name", ""),
            route_long_name=row.get("route_long_name", ""),
            route_color=row.get("route_color", ""),
            route_text_color=row.get("route_text_color", ""),
        )

    def trip_stop_times(self, trip_id: str) -> list[StopTime]:
        return [
            StopTime(
                trip_id=row["trip_id"],
                stop_id=row.get("stop_id", ""),
                arrival_time=row.get("arrival_time", ""),
                departure_time=row.get("departure_time", ""),
                stop_sequence=int(row.get("stop_sequence") or 0),
            )
            for row in self._stop_times_by_trip.get(trip_id, [])
        ]

    def map_realtime_trip(self, trip_id: str) -> dict[str, object]:
        trip = self.lookup_trip(trip_id)
        if not trip:
            return {"trip_id": trip_id, "matched": False}
        route = self.lookup_route(trip.route_id)
        stop_times = self.trip_stop_times(trip_id)
        return {
            "trip_id": trip_id,
            "matched": True,
            "route": route,
            "trip": trip,
            "stop_times": stop_times,
        }

    def next_stop_after_sequence(self, trip_id: str, sequence: int | None) -> StopTime | None:
        if sequence is None:
            return None
        for stop_time in self.trip_stop_times(trip_id):
            if stop_time.stop_sequence >= sequence:
                return stop_time
        return None

    def stop_name(self, stop_id: str) -> str:
        return self._stops_by_id.get(stop_id, {}).get("stop_name", "")

    def _load_table(self, filename: str) -> list[dict[str, str]]:
        if self.zip_path and self.zip_path.exists():
            with zipfile.ZipFile(self.zip_path) as archive:
                try:
                    with archive.open(filename) as handle:
                        text = io.TextIOWrapper(handle, encoding="utf-8-sig")
                        return list(csv.DictReader(text))
                except KeyError:
                    return []
        if self.extracted_dir:
            path = self.extracted_dir / filename
            if path.exists():
                with path.open(newline="", encoding="utf-8-sig") as handle:
                    return list(csv.DictReader(handle))
        return []


def _float_or_none(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None
