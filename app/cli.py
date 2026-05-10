"""Command line interface for NJ TRANSIT rail data."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
from time import sleep

from .api import NjtApiClient
from .gtfs import StaticGtfs
from .gtfsrt import entities_as_dicts, parse_alerts, parse_trip_updates, parse_vehicle_positions
from .utils import PROJECT_ROOT, load_settings, print_rows, write_csv_export, write_json_export


def main() -> None:
    parser = argparse.ArgumentParser(description="NJ TRANSIT rail GTFS/GTFS-RT tools.")
    parser.add_argument("--quiet", action="store_true", help="Suppress auth/API verbose logs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    download = subparsers.add_parser("download", help="Download static GTFS and GTFS-RT rail feeds.")
    download.add_argument("--no-archive", action="store_true", help="Skip timestamped copies in data/archive.")
    download.add_argument("--poll", type=int, default=0, help="Poll every N seconds. Use Ctrl-C to stop.")

    for name in ["alerts", "trips", "vehicles", "stations", "routes"]:
        command = subparsers.add_parser(name, help=f"Show {name}.")
        command.add_argument("--query", default="", help="Filter stations/routes by text.")
        command.add_argument("--limit", type=int, default=30, help="Max rows to print.")
        command.add_argument("--json", dest="json_path", default="", help="Export rows to JSON.")
        command.add_argument("--csv", dest="csv_path", default="", help="Export rows to CSV.")
        if name in {"trips", "vehicles"}:
            command.add_argument("--train-id", default="", help="Filter by GTFS realtime trip/train ID.")

    args = parser.parse_args()

    if args.command == "download":
        settings = load_settings()
        client = NjtApiClient(settings, verbose=not args.quiet)
        while True:
            paths = client.download_all(archive=not args.no_archive)
            for endpoint, path in paths.items():
                print(f"{endpoint}: {path}")
            if not args.poll:
                return
            sleep(args.poll)

    settings = load_settings(require_credentials=False)
    gtfs = StaticGtfs.from_default_sources(settings.gtfs_zip_path)
    raw_dir = settings.raw_dir

    if args.command == "stations":
        rows = [asdict(station) for station in gtfs.stations(args.query)]
        output(rows, ["stop_id", "stop_name", "stop_lat", "stop_lon", "parent_station"], args)
    elif args.command == "routes":
        rows = [asdict(route) for route in gtfs.route_list(args.query)]
        output(rows, ["route_id", "route_short_name", "route_long_name", "route_color"], args)
    elif args.command == "alerts":
        rows = entities_as_dicts(parse_alerts(raw_dir / "alerts.pb"))
        output(rows, ["id", "cause", "effect", "header", "description"], args)
    elif args.command == "trips":
        rows = entities_as_dicts(parse_trip_updates(raw_dir / "trip_updates.pb"))
        rows = enrich_trip_rows(rows, gtfs)
        if args.train_id:
            rows = [row for row in rows if row.get("trip_id") == args.train_id or row.get("id") == args.train_id]
        output(rows, ["trip_id", "route_id", "route_name", "schedule_relationship", "next_stop", "delay_seconds"], args)
    elif args.command == "vehicles":
        rows = entities_as_dicts(parse_vehicle_positions(raw_dir / "vehicle_positions.pb"))
        rows = enrich_vehicle_rows(rows, gtfs)
        if args.train_id:
            rows = [row for row in rows if row.get("trip_id") == args.train_id or row.get("vehicle_id") == args.train_id]
        output(rows, ["vehicle_id", "label", "trip_id", "route_id", "route_name", "current_status", "next_stop", "latitude", "longitude"], args)


def enrich_trip_rows(rows: list[dict], gtfs: StaticGtfs) -> list[dict]:
    for row in rows:
        trip = gtfs.lookup_trip(row.get("trip_id", ""))
        route = gtfs.lookup_route(row.get("route_id", "") or (trip.route_id if trip else ""))
        first_update = (row.get("stop_time_updates") or [{}])[0]
        stop_id = first_update.get("stop_id") or ""
        delay = first_update.get("arrival_delay")
        if delay is None:
            delay = first_update.get("departure_delay")
        row["route_name"] = route.route_long_name if route else ""
        row["next_stop"] = gtfs.stop_name(stop_id)
        row["delay_seconds"] = delay if delay is not None else ""
        row["cancelled"] = row.get("schedule_relationship") == "CANCELED"
    return rows


def enrich_vehicle_rows(rows: list[dict], gtfs: StaticGtfs) -> list[dict]:
    for row in rows:
        trip = gtfs.lookup_trip(row.get("trip_id", ""))
        route = gtfs.lookup_route(row.get("route_id", "") or (trip.route_id if trip else ""))
        next_stop = gtfs.next_stop_after_sequence(row.get("trip_id", ""), row.get("current_stop_sequence"))
        row["route_name"] = route.route_long_name if route else ""
        row["next_stop"] = gtfs.stop_name(row.get("stop_id", "")) or (gtfs.stop_name(next_stop.stop_id) if next_stop else "")
    return rows


def output(rows: list[dict], columns: list[str], args) -> None:
    if args.json_path:
        write_json_export(Path(args.json_path), rows)
        print(f"Wrote JSON: {args.json_path}")
    if args.csv_path:
        write_csv_export(Path(args.csv_path), rows)
        print(f"Wrote CSV: {args.csv_path}")
    print_rows(rows, columns, limit=args.limit)


if __name__ == "__main__":
    main()
