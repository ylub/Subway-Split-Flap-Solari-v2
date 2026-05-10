"""GTFS-Realtime protobuf parsers."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import AlertEntity, TripUpdateEntity, VehiclePositionEntity


def _gtfs_realtime_module():
    try:
        from google.transit import gtfs_realtime_pb2
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "Install GTFS realtime bindings first: python3 -m pip install -r requirements.txt"
        ) from error
    return gtfs_realtime_pb2


def parse_feed(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist. Run `python app.py download` first.")
    payload = path.read_bytes()
    if not payload:
        raise RuntimeError(f"{path} is empty.")
    gtfs_realtime_pb2 = _gtfs_realtime_module()
    feed = gtfs_realtime_pb2.FeedMessage()
    try:
        feed.ParseFromString(payload)
    except Exception as error:
        raise RuntimeError(f"Malformed GTFS-RT protobuf in {path}.") from error
    return feed


def parse_alerts(path: Path) -> list[AlertEntity]:
    rows = []
    for entity in parse_feed(path).entity:
        if not entity.HasField("alert"):
            continue
        alert = entity.alert
        rows.append(
            AlertEntity(
                id=entity.id,
                active_periods=[
                    {"start": period.start if period.HasField("start") else None, "end": period.end if period.HasField("end") else None}
                    for period in alert.active_period
                ],
                informed_entities=[_entity_selector(selector) for selector in alert.informed_entity],
                cause=_enum_name(alert, "cause", alert.cause),
                effect=_enum_name(alert, "effect", alert.effect),
                header=_translated_text(alert.header_text),
                description=_translated_text(alert.description_text),
                url=_translated_text(alert.url),
            )
        )
    return rows


def parse_trip_updates(path: Path) -> list[TripUpdateEntity]:
    rows = []
    for entity in parse_feed(path).entity:
        if not entity.HasField("trip_update"):
            continue
        update = entity.trip_update
        rows.append(
            TripUpdateEntity(
                id=entity.id,
                trip_id=update.trip.trip_id,
                route_id=update.trip.route_id,
                start_time=update.trip.start_time,
                start_date=update.trip.start_date,
                schedule_relationship=_enum_name(update.trip, "schedule_relationship", update.trip.schedule_relationship),
                vehicle_id=update.vehicle.id,
                stop_time_updates=[_stop_time_update(item) for item in update.stop_time_update],
            )
        )
    return rows


def parse_vehicle_positions(path: Path) -> list[VehiclePositionEntity]:
    rows = []
    for entity in parse_feed(path).entity:
        if not entity.HasField("vehicle"):
            continue
        vehicle = entity.vehicle
        position = vehicle.position if vehicle.HasField("position") else None
        rows.append(
            VehiclePositionEntity(
                id=entity.id,
                trip_id=vehicle.trip.trip_id,
                route_id=vehicle.trip.route_id,
                start_time=vehicle.trip.start_time,
                start_date=vehicle.trip.start_date,
                vehicle_id=vehicle.vehicle.id,
                label=vehicle.vehicle.label,
                current_stop_sequence=vehicle.current_stop_sequence if vehicle.HasField("current_stop_sequence") else None,
                stop_id=vehicle.stop_id,
                current_status=_enum_name(vehicle, "current_status", vehicle.current_status),
                timestamp=vehicle.timestamp if vehicle.HasField("timestamp") else None,
                latitude=position.latitude if position and position.HasField("latitude") else None,
                longitude=position.longitude if position and position.HasField("longitude") else None,
                bearing=position.bearing if position and position.HasField("bearing") else None,
                speed=position.speed if position and position.HasField("speed") else None,
            )
        )
    return rows


def entities_as_dicts(rows: list[Any]) -> list[dict[str, Any]]:
    return [asdict(row) for row in rows]


def _translated_text(message) -> str:
    if not message.translation:
        return ""
    english = [item.text for item in message.translation if item.language.lower().startswith("en")]
    return english[0] if english else message.translation[0].text


def _entity_selector(selector) -> dict[str, str]:
    return {
        "agency_id": selector.agency_id,
        "route_id": selector.route_id,
        "route_type": str(selector.route_type) if selector.HasField("route_type") else "",
        "trip_id": selector.trip.trip_id,
        "stop_id": selector.stop_id,
    }


def _stop_time_update(item) -> dict[str, Any]:
    return {
        "stop_sequence": item.stop_sequence if item.HasField("stop_sequence") else None,
        "stop_id": item.stop_id,
        "schedule_relationship": _enum_name(item, "schedule_relationship", item.schedule_relationship),
        "arrival_time": item.arrival.time if item.HasField("arrival") and item.arrival.HasField("time") else None,
        "arrival_delay": item.arrival.delay if item.HasField("arrival") and item.arrival.HasField("delay") else None,
        "departure_time": item.departure.time if item.HasField("departure") and item.departure.HasField("time") else None,
        "departure_delay": item.departure.delay if item.HasField("departure") and item.departure.HasField("delay") else None,
    }


def _enum_name(message, field_name: str, value: int) -> str:
    field = message.DESCRIPTOR.fields_by_name[field_name]
    enum_value = field.enum_type.values_by_number.get(value)
    return enum_value.name if enum_value else str(value)
