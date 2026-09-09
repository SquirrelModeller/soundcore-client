"""Connect-time snapshot parsing (DEVICE-INFO.md).

The snapshot (`device_info_reply`, group 0x01 / command 0x01) is **per model**.
Three container styles exist: FIX (flat offsets), BB (same order, streamed cursor),
TLV (tag/length/value). Only the *leading blocks* are stable across the ~40 FIX/BB
parsers; the tail is genuinely per-model.

This module provides:
  * `parse_leading_blocks()` -- the stable FIX/BB head (host/TWS/battery/charging/
    firmware/serial), returned for any model even without a tail table.
  * `parse_tlv()` -- the TLV container with the common tag catalogue.
  * helpers for the EQ-index sentinels and the biased inbound curve.

Frame offsets are used throughout (payload offset + 9), matching the parsers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..protocol import GraphicEqCurve, clamp_battery
from ..protocol.constants import (
    EQ_INDEX_CUSTOM,
    EQ_INDEX_FORCE_2,
    EQ_INDEX_NAMED_GROUP,
    EQ_PRESET_INDEX_MAX,
)

# AeroFit open earbuds omit the two charging bytes.
NO_CHARGING_BYTES = frozenset({"a3875", "a3876", "a3878", "a3871", "a3874"})
# speakers with a 17-char serial instead of 16.
SERIAL_17 = frozenset({"d5100", "d5103"})


@dataclass
class DeviceInfo:
    """Decoded snapshot. `tail` holds model-specific fields when a table exists;
    `partial` is True when only the leading blocks were understood."""

    model: str | None = None
    style: str = "FIX"
    partial: bool = True
    host_side: int | None = None
    tws_present: bool | None = None
    left_battery: int | None = None
    right_battery: int | None = None
    case_battery: int | None = None
    left_charging: bool | None = None
    right_charging: bool | None = None
    left_firmware: str | None = None
    right_firmware: str | None = None
    case_firmware: str | None = None
    serial: str | None = None
    eq_index: int | None = None
    eq_type: str | None = None
    eq_curve: GraphicEqCurve | None = None
    tail: dict[str, object] = field(default_factory=dict)
    raw: bytes | None = None


def decode_eq_index(le16: int) -> tuple[int, str]:
    """Resolve the active-EQ-index LE16 and its high-byte sentinel.

    Returns `(index, kind)` where kind is one of
    "custom" / "named_group" / "force_2" / "preset".
    """
    hi = (le16 >> 8) & 0xFF
    if hi == EQ_INDEX_CUSTOM:
        return le16 & 0xFF, "custom"
    if hi == EQ_INDEX_NAMED_GROUP:
        return le16 - 0xEE00, "named_group"  # then remapped by a model table
    if hi == EQ_INDEX_FORCE_2:
        return 2, "force_2"
    return max(0, min(EQ_PRESET_INDEX_MAX, le16)), "preset"


def _ascii(raw: bytes, start: int, length: int) -> str:
    return raw[start : start + length].decode("ascii", "replace").rstrip("\x00")


def parse_leading_blocks(raw: bytes, *, model: str | None = None) -> DeviceInfo:
    """Parse the stable FIX/BB head. Safe for any FIX/BB model; leaves `partial`
    True and does not touch the per-model tail."""
    info = DeviceInfo(model=model, raw=raw)
    has_charging = model not in NO_CHARGING_BYTES if model else True
    serial_len = 17 if model in SERIAL_17 else 16

    o = 9
    info.host_side = raw[o]
    info.tws_present = raw[o + 1] != 0
    info.left_battery = clamp_battery(raw[o + 2])
    info.right_battery = clamp_battery(raw[o + 3])
    o += 4
    if has_charging:
        info.left_charging = raw[o] != 0
        info.right_charging = raw[o + 1] != 0
        o += 2
    info.left_firmware = _ascii(raw, o, 5)
    info.right_firmware = _ascii(raw, o + 5, 5)
    o += 10
    info.serial = _ascii(raw, o, serial_len)
    return info


# --- TLV container (DEVICE-INFO.md section 1.3) ------------------------------

_TLV_COMMON = {
    0x01: "host_side",
    0x02: "tws_present",
    0x03: "left",  # [charging bool, battery u8]
    0x04: "right",
    0x05: "left_firmware",
    0x06: "right_firmware",
    0x07: "serial",
    0x08: "case",  # [charging bool, battery u8]
    0x09: "case_firmware",
    0x0A: "colour_code",
    0x0B: "eq_index",  # 2 bytes lo, hi -- sentinels as above
    0x0C: "eq_curve",  # 10 bytes, biased/unsigned
}


def iter_tlv(raw: bytes):
    """Yield `(tag, value_bytes)` records from a TLV snapshot; stop on truncation."""
    i = 9
    n = len(raw) - 1  # trailing checksum is outside the container
    while i + 2 <= n:
        tag = raw[i]
        length = raw[i + 1]
        if i + 2 + length > n:
            break
        yield tag, raw[i + 2 : i + 2 + length]
        i += 2 + length


def parse_tlv(raw: bytes, *, model: str | None = None) -> DeviceInfo:
    """Parse a TLV snapshot using the common tag catalogue. Unknown tags are
    collected under `tail['tags']` as hex for later analysis."""
    info = DeviceInfo(model=model, style="TLV", raw=raw)
    unknown: dict[int, str] = {}
    for tag, value in iter_tlv(raw):
        name = _TLV_COMMON.get(tag)
        if name == "host_side":
            info.host_side = value[0]
        elif name == "tws_present":
            info.tws_present = value[0] != 0
        elif name == "left":
            info.left_charging = value[0] != 0
            info.left_battery = clamp_battery(value[1])
        elif name == "right":
            info.right_charging = value[0] != 0
            info.right_battery = clamp_battery(value[1])
        elif name == "case":
            info.case_battery = clamp_battery(value[1])
        elif name == "left_firmware":
            info.left_firmware = value.decode("ascii", "replace").rstrip("\x00")
        elif name == "right_firmware":
            info.right_firmware = value.decode("ascii", "replace").rstrip("\x00")
        elif name == "case_firmware":
            info.case_firmware = value.decode("ascii", "replace").rstrip("\x00")
        elif name == "serial":
            info.serial = value.decode("ascii", "replace").rstrip("\x00")
        elif name == "eq_index" and len(value) >= 2:
            info.eq_index, info.eq_type = decode_eq_index(value[0] | (value[1] << 8))
        elif name == "eq_curve":
            info.eq_curve = GraphicEqCurve.from_inbound(value)
        elif name == "colour_code":
            info.tail["colour_code"] = value.decode("ascii", "replace")
        else:
            unknown[tag] = value.hex()
    if unknown:
        info.tail["tags"] = unknown
    return info
