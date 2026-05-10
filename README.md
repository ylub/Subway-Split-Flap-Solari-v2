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

## NJ TRANSIT Rail Live Data

NJ TRANSIT rail can be used as a Solari feed with cached API downloads:

```bash
cp .env.example .env
# edit .env and set NJT_USERNAME / NJT_PASSWORD
python3 -m pip install -r requirements.txt
python3 solari.py download-njt
python3 solari.py serve
```

`download-njt` uses the rail API documented in `gtfs/njt/NJTRANSIT_Rail_GTFSRT_V1.pdf`:

- POST multipart/form-data `username` and `password` to `getToken`
- cache token metadata in `config/njt_token.json`
- reuse the cached token until it locally expires or the API returns `Invalid token`
- POST multipart/form-data `token` to `getGTFS`, `getAlerts`, `getTripUpdates`, and `getVehiclePositions`

Downloads are saved under `data/raw/`:

- `rail_gtfs.zip`
- `alerts.pb`
- `trip_updates.pb`
- `vehicle_positions.pb`

Timestamped copies are also saved under `data/archive/` unless `--no-archive` is passed.

The `njt_rail` Solari feed reads `data/raw/rail_gtfs.zip` when available, falling back to the local `gtfs/njt/rail_data/` sample. If `data/raw/trip_updates.pb` exists and `gtfs-realtime-bindings` is installed, NJT rail departures show realtime delay/cancel status on the board.

To refresh only realtime protobuf feeds without downloading static GTFS:

```bash
python3 solari.py refresh-njt
```

The helper CLI also exposes inspection commands:

```bash
python3 app.py stations --query penn
python3 app.py routes
python3 app.py alerts
python3 app.py trips --train-id 1234
python3 app.py vehicles
```
