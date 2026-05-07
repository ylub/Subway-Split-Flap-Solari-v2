# GTFS Solari

A local multi-feed GTFS split-flap departure board based on David Tropiansky's MIT-licensed Subway Split-Flap Solari v2 frontend.

Python reads local GTFS feeds under `gtfs/`, exposes JSON endpoints, and serves the browser board. The frontend uses the v2 GitHub project's `split-flap.js`, base CSS, flap sprite sheet, and status light images, with a local adapter for feed selection, route badges, and GTFS line colors. See `THIRD_PARTY_NOTICES.md` for attribution and data notes.

GTFS feeds are kept under `gtfs/`:

- `gtfs/lirr/`
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

Use the feed selector in the browser, then choose a station/stop from that feed.

## API

```text
/api/feeds
/api/stations?feed=lirr
/api/departures?feed=lirr&station=Jamaica&limit=12
/api/departures?feed=subway&station=Times%20Sq-42%20St&limit=12
/api/departures?feed=manhattan_bus&station=E%2034%20ST/5%20AV&limit=12
/api/departures?feed=metro_north&station=Grand%20Central&limit=12
```

Each departure includes:

- `route_id`
- `route_name`
- `route_symbol`
- `route_color`
- `route_text_color`
- `destination`
- `departure_time`
- `minutes`
- `status`

The current version is based on static GTFS schedules, so status is shown as `Scheduled`.
