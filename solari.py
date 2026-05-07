#!/usr/bin/env python3
"""Split-flap departure board powered by local GTFS feeds."""

from __future__ import annotations

import argparse
import csv
import json
import math
import mimetypes
import re
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from zoneinfo import ZoneInfo


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
GTFS_ROOT = BASE_DIR / "gtfs"
FEED_TZ = ZoneInfo("America/New_York")
STATION_CLUSTER_METERS = 350


def clean(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def parse_gtfs_time(value: str) -> int:
    hours, minutes, seconds = [int(part) for part in value.split(":")]
    return hours * 3600 + minutes * 60 + seconds


def format_gtfs_time(seconds: int) -> str:
    hours = (seconds // 3600) % 24
    minutes = (seconds % 3600) // 60
    suffix = "AM" if hours < 12 else "PM"
    display_hour = hours % 12 or 12
    return f"{display_hour}:{minutes:02d} {suffix}"


def distance_meters(first: dict[str, str], second: dict[str, str]) -> float | None:
    try:
        first_lat = math.radians(float(first["stop_lat"]))
        first_lon = math.radians(float(first["stop_lon"]))
        second_lat = math.radians(float(second["stop_lat"]))
        second_lon = math.radians(float(second["stop_lon"]))
    except (KeyError, TypeError, ValueError):
        return None

    lat_delta = second_lat - first_lat
    lon_delta = second_lon - first_lon
    a = math.sin(lat_delta / 2) ** 2 + math.cos(first_lat) * math.cos(second_lat) * math.sin(lon_delta / 2) ** 2
    return 6371000 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


@dataclass(frozen=True)
class FeedConfig:
    key: str
    label: str
    path: Path
    default_station: str
    route_name_field: str = "route_long_name"
    route_symbol_field: str = "route_short_name"
    use_transfer_clusters: bool = False


@dataclass(frozen=True)
class Departure:
    route_id: str
    route_name: str
    route_symbol: str
    route_color: str
    route_text_color: str
    destination: str
    trip_id: str
    trip_short_name: str
    direction_id: str
    departure_seconds: int
    minutes: int
    peak_offpeak: str


class GtfsSchedule:
    def __init__(self, config: FeedConfig) -> None:
        self.config = config
        self.gtfs_dir = config.path
        self.routes = self._load_routes()
        self.stops = self._load_stops()
        self.transfer_parent_ids = self._load_transfer_parent_ids()
        self.trips = self._load_trips()
        self.calendar_services = self._load_calendar()
        self.service_exceptions = self._load_service_exceptions()
        self.stop_times_by_stop = self._load_stop_times()

    def _load_routes(self) -> dict[str, dict[str, str]]:
        routes = {}
        for row in read_csv(self.gtfs_dir / "routes.txt"):
            name = row.get(self.config.route_name_field, "") or row.get("route_short_name", "") or row.get("route_long_name", "")
            symbol = row.get(self.config.route_symbol_field, "") or row.get("route_short_name", "") or name or row["route_id"]
            routes[row["route_id"]] = {
                "name": name or row["route_id"],
                "symbol": symbol,
                "color": f"#{row.get('route_color', '').lstrip('#') or '555555'}",
                "text_color": f"#{row.get('route_text_color', '').lstrip('#') or 'FFFFFF'}",
            }
        return routes

    def _load_stops(self) -> dict[str, dict[str, str]]:
        stops = {}
        for row in read_csv(self.gtfs_dir / "stops.txt"):
            row["search_key"] = clean(row["stop_name"])
            stops[row["stop_id"]] = row
        return stops

    def _load_transfer_parent_ids(self) -> dict[str, set[str]]:
        if not self.config.use_transfer_clusters:
            return {}

        parent_ids: dict[str, set[str]] = {}
        for row in read_csv(self.gtfs_dir / "transfers.txt"):
            from_parent = self.parent_id_for_stop_id(row.get("from_stop_id", ""))
            to_parent = self.parent_id_for_stop_id(row.get("to_stop_id", ""))
            if not from_parent or not to_parent or from_parent == to_parent:
                continue
            parent_ids.setdefault(from_parent, set()).add(to_parent)
            parent_ids.setdefault(to_parent, set()).add(from_parent)
        return parent_ids

    def _load_trips(self) -> dict[str, dict[str, str]]:
        return {row["trip_id"]: row for row in read_csv(self.gtfs_dir / "trips.txt")}

    def _load_calendar(self) -> list[dict[str, str]]:
        return read_csv(self.gtfs_dir / "calendar.txt")

    def _load_service_exceptions(self) -> dict[str, dict[str, set[str]]]:
        exceptions: dict[str, dict[str, set[str]]] = {}
        for row in read_csv(self.gtfs_dir / "calendar_dates.txt"):
            action = "added" if row.get("exception_type") == "1" else "removed"
            exceptions.setdefault(row["date"], {"added": set(), "removed": set()})[action].add(row["service_id"])
        return exceptions

    def active_services(self, current: datetime) -> set[str]:
        service_date = current.strftime("%Y%m%d")
        weekday = current.strftime("%A").lower()
        active: set[str] = set()

        for row in self.calendar_services:
            if row.get("start_date", "") <= service_date <= row.get("end_date", "") and row.get(weekday) == "1":
                active.add(row["service_id"])

        exceptions = self.service_exceptions.get(service_date)
        if exceptions:
            active.update(exceptions["added"])
            active.difference_update(exceptions["removed"])

        return active

    def _load_stop_times(self) -> dict[str, list[dict[str, str | int]]]:
        by_stop: dict[str, list[dict[str, str | int]]] = {}
        for row in read_csv(self.gtfs_dir / "stop_times.txt"):
            trip = self.trips.get(row["trip_id"])
            if not trip:
                continue
            entry: dict[str, str | int] = {
                "trip_id": row["trip_id"],
                "service_id": trip["service_id"],
                "departure_seconds": parse_gtfs_time(row["departure_time"]),
            }
            by_stop.setdefault(row["stop_id"], []).append(entry)

        for entries in by_stop.values():
            entries.sort(key=lambda item: int(item["departure_seconds"]))
        return by_stop

    def station_options(self) -> list[dict[str, str]]:
        seen = set()
        stations = []
        for stop_id, row in self.stops.items():
            key = (row["stop_name"], row.get("stop_code", ""))
            if key in seen:
                continue
            seen.add(key)
            stations.append(
                {
                    "stop_id": stop_id,
                    "stop_code": row.get("stop_code", ""),
                    "stop_name": row["stop_name"],
                }
            )
        return sorted(stations, key=lambda row: row["stop_name"])

    def find_stop(self, query: str) -> dict[str, str] | None:
        query_key = clean(query)
        if query in self.stops:
            return self.stops[query]

        for row in self.stops.values():
            if query_key and query_key in {row["search_key"], clean(row.get("stop_code", ""))}:
                return row

        matches = [
            row
            for row in self.stops.values()
            if query_key and (query_key in row["search_key"] or query_key in clean(row.get("stop_code", "")))
        ]
        return sorted(matches, key=lambda row: len(row["stop_name"]))[0] if matches else None

    def departures(self, station: str, limit: int = 12, now: datetime | None = None) -> tuple[dict[str, str], list[Departure]]:
        current = now.astimezone(FEED_TZ) if now else datetime.now(FEED_TZ)
        active_services = self.active_services(current)
        stop = self.find_stop(station)
        if not stop:
            raise ValueError(f"No {self.config.label} stop matched {station!r}.")

        midnight = current.replace(hour=0, minute=0, second=0, microsecond=0)
        now_seconds = int((current - midnight).total_seconds())
        departures: list[Departure] = []

        for stop_id in self.stop_ids_for(stop):
            for row in self.stop_times_by_stop.get(stop_id, []):
                if row["service_id"] not in active_services:
                    continue

                departure_seconds = int(row["departure_seconds"])
                if departure_seconds < now_seconds:
                    continue

                trip = self.trips[str(row["trip_id"])]
                route = self.routes.get(trip["route_id"], {})
                minutes = max(0, round((departure_seconds - now_seconds) / 60))
                departures.append(
                    Departure(
                        route_id=trip["route_id"],
                        route_name=route.get("name", trip["route_id"]),
                        route_symbol=route.get("symbol", trip["route_id"]),
                        route_color=route.get("color", "#555555"),
                        route_text_color=route.get("text_color", "#FFFFFF"),
                        destination=trip.get("trip_headsign", self.config.label),
                        trip_id=trip["trip_id"],
                        trip_short_name=trip.get("trip_short_name", ""),
                        direction_id=trip.get("direction_id", ""),
                        departure_seconds=departure_seconds,
                        minutes=minutes,
                        peak_offpeak=trip.get("peak_offpeak", ""),
                    )
                )

        departures.sort(key=lambda item: item.departure_seconds)
        departures = departures[:limit]
        return stop, departures

    def stop_ids_for(self, stop: dict[str, str]) -> list[str]:
        parent = self.parent_stop_for(stop)
        stop_ids: list[str] = []
        for parent_id in self.station_cluster_parent_ids(parent):
            if parent_id in self.stop_times_by_stop:
                stop_ids.append(parent_id)
            stop_ids.extend(
                candidate_id
                for candidate_id, row in self.stops.items()
                if row.get("parent_station") == parent_id and candidate_id in self.stop_times_by_stop
            )
        return stop_ids or [stop["stop_id"]]

    def parent_stop_for(self, stop: dict[str, str]) -> dict[str, str]:
        parent_id = stop.get("parent_station")
        if parent_id and parent_id in self.stops:
            return self.stops[parent_id]
        return stop

    def parent_id_for_stop_id(self, stop_id: str) -> str | None:
        stop = self.stops.get(stop_id)
        if not stop:
            return None
        return stop.get("parent_station") or stop_id

    def station_cluster_parent_ids(self, parent: dict[str, str]) -> list[str]:
        same_name_candidates = {
            candidate_id: candidate
            for candidate_id, candidate in self.stops.items()
            if not candidate.get("parent_station") and candidate.get("search_key") == parent.get("search_key")
        }
        parent_id = parent["stop_id"]
        parent_ids = [parent_id]
        seen = {parent_id}
        index = 0
        while index < len(parent_ids):
            current_id = parent_ids[index]
            current = self.stops[current_id]
            index += 1

            for candidate_id in self.transfer_parent_ids.get(current_id, set()):
                if candidate_id not in seen and candidate_id in self.stops:
                    seen.add(candidate_id)
                    parent_ids.append(candidate_id)

            for candidate_id, candidate in same_name_candidates.items():
                if candidate_id in seen:
                    continue
                distance = distance_meters(current, candidate)
                if distance is not None and distance <= STATION_CLUSTER_METERS:
                    seen.add(candidate_id)
                    parent_ids.append(candidate_id)

        return parent_ids


FEEDS: dict[str, FeedConfig] = {
    "lirr": FeedConfig("lirr", "Long Island Rail Road", GTFS_ROOT / "lirr", "Jamaica", route_symbol_field="route_long_name"),
    "subway": FeedConfig("subway", "NYC Subway", GTFS_ROOT / "subway", "Times Sq-42 St", "route_short_name", use_transfer_clusters=True),
    "subway_supplemented": FeedConfig(
        "subway_supplemented",
        "NYC Subway Supplemented",
        GTFS_ROOT / "subway_supplemented",
        "Times Sq-42 St",
        "route_short_name",
        use_transfer_clusters=True,
    ),
    "manhattan_bus": FeedConfig("manhattan_bus", "Manhattan Bus", GTFS_ROOT / "manhattan_bus", "E 34 ST/5 AV", "route_short_name"),
    "metro_north": FeedConfig("metro_north", "Metro-North Railroad", GTFS_ROOT / "metro_north", "Grand Central", "route_short_name"),
}

SCHEDULES: dict[str, GtfsSchedule] = {}


def feed_options() -> list[dict[str, str]]:
    return [
        {"key": config.key, "label": config.label, "default_station": config.default_station}
        for config in FEEDS.values()
        if config.path.exists()
    ]


def get_schedule(feed_key: str) -> GtfsSchedule:
    config = FEEDS.get(feed_key)
    if not config:
        raise ValueError(f"Unknown feed {feed_key!r}.")
    if not config.path.exists():
        raise ValueError(f"GTFS feed {feed_key!r} is not available at {config.path}.")
    if feed_key not in SCHEDULES:
        print(f"Loading {config.label} GTFS from: {config.path}")
        SCHEDULES[feed_key] = GtfsSchedule(config)
    return SCHEDULES[feed_key]


get_schedule("lirr")


class SolariHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/departures":
            self.send_departures(parsed.query)
            return
        if parsed.path == "/api/feeds":
            self.send_json({"feeds": feed_options()})
            return
        if parsed.path == "/api/stations":
            self.send_stations(parsed.query)
            return

        relative = "index.html" if parsed.path in {"/", ""} else unquote(parsed.path.lstrip("/"))
        path = (STATIC_DIR / relative).resolve()
        if STATIC_DIR not in path.parents and path != STATIC_DIR:
            self.send_error(403)
            return
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_departures(self, query: str) -> None:
        params = parse_qs(query)
        feed_key = params.get("feed", ["lirr"])[0]
        try:
            schedule = get_schedule(feed_key)
        except ValueError as error:
            self.send_json({"error": str(error)}, status=404)
            return

        station = params.get("station", [schedule.config.default_station])[0]
        limit = min(24, max(1, int(params.get("limit", ["12"])[0])))

        try:
            stop, departures = schedule.departures(station, limit=limit)
        except ValueError as error:
            self.send_json({"error": str(error)}, status=404)
            return

        self.send_json(
            {
                "feed": {
                    "key": schedule.config.key,
                    "label": schedule.config.label,
                    "default_station": schedule.config.default_station,
                },
                "station": {
                    "stop_id": stop["stop_id"],
                    "stop_code": stop.get("stop_code", ""),
                    "stop_name": stop["stop_name"],
                },
                "generated_at": datetime.now(FEED_TZ).isoformat(),
                "departures": [
                    {
                        "route_id": item.route_id,
                        "route_name": item.route_name,
                        "route_symbol": item.route_symbol,
                        "route_color": item.route_color,
                        "route_text_color": item.route_text_color,
                        "destination": item.destination,
                        "departure_time": format_gtfs_time(item.departure_seconds),
                        "minutes": item.minutes,
                        "status": "Scheduled",
                        "trip_id": item.trip_id,
                        "trip_short_name": item.trip_short_name,
                        "direction_id": item.direction_id,
                        "peak_offpeak": item.peak_offpeak,
                    }
                    for item in departures
                ],
            }
        )

    def send_stations(self, query: str) -> None:
        params = parse_qs(query)
        feed_key = params.get("feed", ["lirr"])[0]
        try:
            schedule = get_schedule(feed_key)
        except ValueError as error:
            self.send_json({"error": str(error)}, status=404)
            return

        self.send_json(
            {
                "feed": {
                    "key": schedule.config.key,
                    "label": schedule.config.label,
                    "default_station": schedule.config.default_station,
                },
                "stations": schedule.station_options(),
            }
        )

    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the GTFS Solari departure board.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), SolariHandler)
    print(f"GTFS Solari board: http://{args.host}:{args.port}")
    print("Available feeds: " + ", ".join(option["key"] for option in feed_options()))
    server.serve_forever()


if __name__ == "__main__":
    main()
