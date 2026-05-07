#!/usr/bin/env python3
"""LIRR split-flap departure board powered by a local GTFS feed."""

from __future__ import annotations

import argparse
import csv
import json
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
GTFS_DIR = BASE_DIR / "gtfs" / "lirr"
FEED_TZ = ZoneInfo("America/New_York")


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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


@dataclass(frozen=True)
class Departure:
    route_id: str
    route_name: str
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
    def __init__(self, gtfs_dir: Path) -> None:
        self.gtfs_dir = gtfs_dir
        self.routes = self._load_routes()
        self.stops = self._load_stops()
        self.trips = self._load_trips()
        self.services_by_date = self._load_services()
        self.stop_times_by_stop = self._load_stop_times()

    def _load_routes(self) -> dict[str, dict[str, str]]:
        routes = {}
        for row in read_csv(self.gtfs_dir / "routes.txt"):
            routes[row["route_id"]] = {
                "name": row["route_long_name"],
                "color": f"#{row['route_color'].lstrip('#')}",
                "text_color": f"#{row['route_text_color'].lstrip('#')}",
            }
        return routes

    def _load_stops(self) -> dict[str, dict[str, str]]:
        stops = {}
        for row in read_csv(self.gtfs_dir / "stops.txt"):
            row["search_key"] = clean(row["stop_name"])
            stops[row["stop_id"]] = row
        return stops

    def _load_trips(self) -> dict[str, dict[str, str]]:
        return {row["trip_id"]: row for row in read_csv(self.gtfs_dir / "trips.txt")}

    def _load_services(self) -> dict[str, set[str]]:
        services: dict[str, set[str]] = {}
        for row in read_csv(self.gtfs_dir / "calendar_dates.txt"):
            if row.get("exception_type") == "1":
                services.setdefault(row["date"], set()).add(row["service_id"])
        return services

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
        return sorted(
            [
                {
                    "stop_id": stop_id,
                    "stop_code": row.get("stop_code", ""),
                    "stop_name": row["stop_name"],
                }
                for stop_id, row in self.stops.items()
            ],
            key=lambda row: row["stop_name"],
        )

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
        service_date = current.strftime("%Y%m%d")
        active_services = self.services_by_date.get(service_date, set())
        stop = self.find_stop(station)
        if not stop:
            raise ValueError(f"No LIRR stop matched {station!r}.")

        midnight = current.replace(hour=0, minute=0, second=0, microsecond=0)
        now_seconds = int((current - midnight).total_seconds())
        departures: list[Departure] = []

        for row in self.stop_times_by_stop.get(stop["stop_id"], []):
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
                    route_color=route.get("color", "#555555"),
                    route_text_color=route.get("text_color", "#FFFFFF"),
                    destination=trip.get("trip_headsign", "LIRR"),
                    trip_id=trip["trip_id"],
                    trip_short_name=trip.get("trip_short_name", ""),
                    direction_id=trip.get("direction_id", ""),
                    departure_seconds=departure_seconds,
                    minutes=minutes,
                    peak_offpeak=trip.get("peak_offpeak", ""),
                )
            )
            if len(departures) >= limit:
                break

        return stop, departures


schedule = GtfsSchedule(GTFS_DIR)


class SolariHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/departures":
            self.send_departures(parsed.query)
            return
        if parsed.path == "/api/stations":
            self.send_json({"stations": schedule.station_options()})
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
        station = params.get("station", ["Jamaica"])[0]
        limit = min(24, max(1, int(params.get("limit", ["12"])[0])))

        try:
            stop, departures = schedule.departures(station, limit=limit)
        except ValueError as error:
            self.send_json({"error": str(error)}, status=404)
            return

        self.send_json(
            {
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
    parser = argparse.ArgumentParser(description="Run the LIRR Solari departure board.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), SolariHandler)
    print(f"LIRR Solari board: http://{args.host}:{args.port}")
    print(f"Reading GTFS from: {GTFS_DIR}")
    server.serve_forever()


if __name__ == "__main__":
    main()
