"""A rolling view of device state assembled from inbound events."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .deviceinfo import DeviceInfo
from .events import ParsedEvent

_Bag = Mapping[str, object]


def _as_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _as_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


@dataclass
class DeviceState:
    """Best-effort current state. Every parsed event is folded in; `events` keeps
    the most recent fields per event name for anything without a dedicated slot."""

    device_info: DeviceInfo | None = None
    left_battery: int | None = None
    right_battery: int | None = None
    case_battery: int | None = None
    left_charging: bool | None = None
    right_charging: bool | None = None
    ambient: _Bag | None = None
    eq: _Bag | None = None
    spatial_audio: _Bag | None = None
    events: dict[str, _Bag] = field(default_factory=dict)

    def apply(self, ev: ParsedEvent) -> None:
        self.events[ev.name] = ev.fields
        f = ev.fields
        if ev.name == "battery_changed":
            self.left_battery = _as_int(f.get("left_battery"))
            self.right_battery = _as_int(f.get("right_battery"))
            self.case_battery = _as_int(f.get("case_battery"))
        elif ev.name == "charging_changed":
            self.left_charging = _as_bool(f.get("left_charging"))
            self.right_charging = _as_bool(f.get("right_charging"))
        elif ev.name == "ambient_details_reply":
            self.ambient = f
        elif ev.name == "eq_reply":
            self.eq = f
        elif ev.name == "spatial_audio_reply":
            self.spatial_audio = f
