# LIRR Solari

A local Long Island Rail Road split-flap departure board based on David Tropiansky's MIT-licensed Subway Split-Flap Solari v2 frontend.

Python reads the local LIRR GTFS feed in `gtfs/lirr/`, exposes JSON endpoints, and serves the browser board. The frontend uses the v2 GitHub project's `split-flap.js`, base CSS, flap sprite sheet, and status light images, with a local `plugins/lirr/` adapter for LIRR branch names and GTFS line colors. See `THIRD_PARTY_NOTICES.md` for attribution and data notes.

Additional GTFS feeds are kept under `gtfs/`:

- `gtfs/subway/`
- `gtfs/subway_supplemented/`
- `gtfs/manhattan_bus/`
- `gtfs/metro_north/`

## Run

```bash
cd /Users/yitzchak/Documents/Python/solari
python3 solari.py
```

Then open:

```text
http://127.0.0.1:8080
```

Use a station name such as `Jamaica`, `Far Rockaway`, `Penn Station`, `Grand Central`, `Cedarhurst`, or `Woodmere`.

## API

```text
/api/stations
/api/departures?station=Jamaica&limit=12
```

Each departure includes:

- `route_name`
- `route_color`
- `route_text_color`
- `destination`
- `departure_time`
- `minutes`
- `status`

The current version is based on static GTFS schedules, so status is shown as `Scheduled`.
