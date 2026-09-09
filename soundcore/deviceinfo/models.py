"""Per-model snapshot tail parsers (DEVICE-INFO.md section 3).

Only a handful of models are tabulated here as worked examples; the rest fall back
to `parse_leading_blocks` / `parse_tlv`. Adding a model = one function + one
registry entry. Frame offsets throughout.
"""

from __future__ import annotations

from ..protocol import GraphicEqCurve
from .common import DeviceInfo, decode_eq_index, parse_leading_blocks

MODE_SELECT_BITS = ("nc_selected", "transp_selected", "normal_selected", "adaptive_selected")


def _mode_select(byte: int) -> dict[str, object]:
    out: dict[str, object] = {name: bool(byte & (1 << i)) for i, name in enumerate(MODE_SELECT_BITS)}
    out["raw"] = byte
    return out


def _eq_at(raw: bytes, lo_off: int) -> tuple[int, str]:
    return decode_eq_index(raw[lo_off] | (raw[lo_off + 1] << 8))


# --- a6610 (Sleep-series earbud, Style FIX, no gesture-length byte) ---------

def parse_a6610(raw: bytes) -> DeviceInfo:
    info = parse_leading_blocks(raw, model="a6610")
    info.left_charging = raw[13] != 0
    info.right_charging = raw[14] != 0
    info.eq_index, info.eq_type = _eq_at(raw, 41)
    info.eq_curve = GraphicEqCurve.from_inbound(raw[43:53])
    t = info.tail
    t["mode_select"] = _mode_select(raw[75])
    t["current_mode"] = raw[76]
    t["smart_play_pause_on_removal"] = raw[77] != 0
    t["custom_play_time"] = raw[78]
    t["adaptive_nc"] = raw[79] != 0
    t["voice_prompt"] = raw[80] != 0
    t["colour_code"] = chr(raw[81]) if 32 <= raw[81] < 127 else raw[81]
    t["sleep_sound_id"] = raw[82]
    t["sleep_sound_present"] = raw[83] != 0
    t["sleep_sound_volume"] = raw[84]
    if len(raw) >= 87:
        t["press_sensitivity"] = raw[85]
    if len(raw) >= 89:
        t["play_countdown_minutes"] = (raw[86] << 8) | raw[87]  # BE16
    info.partial = False
    return info


# --- a3040 (Space-series earbud, Style FIX, single battery, gesture-length C) ---

def parse_a3040(raw: bytes) -> DeviceInfo:
    info = DeviceInfo(model="a3040", style="FIX", raw=raw)
    info.left_battery = info.right_battery = raw[9]
    info.left_charging = info.right_charging = raw[10] != 0
    info.left_firmware = raw[11:16].decode("ascii", "replace").rstrip("\x00")
    info.serial = raw[16:32].decode("ascii", "replace").rstrip("\x00")
    info.eq_index, info.eq_type = _eq_at(raw, 32)
    info.eq_curve = GraphicEqCurve.from_inbound(raw[34:44])
    c = raw[54]
    t = info.tail
    t["gesture_length"] = c
    base = 54 + c
    try:
        t["mode_select"] = _mode_select(raw[base - 1])
        t["touch_tone"] = raw[base + 6] != 0
        t["wear_detection"] = raw[base + 7] != 0
        t["three_d_effect"] = raw[base + 8] != 0
        t["case_battery"] = raw[base + 9]
        t["bass_up"] = raw[base + 10] != 0
        t["colour_code"] = chr(raw[base + 11]) if 32 <= raw[base + 11] < 127 else raw[base + 11]
        t["ldac"] = raw[base + 12] != 0
        t["dual_device_connection"] = raw[base + 13] != 0
        info.partial = False
    except IndexError:
        info.partial = True
    return info


# --- a3994 (Liberty-series earbud, Style BB, minimal tail) ----------------

def parse_a3994(raw: bytes) -> DeviceInfo:
    info = parse_leading_blocks(raw, model="a3994")
    info.left_charging = raw[13] != 0
    info.right_charging = raw[14] != 0
    info.style = "BB"
    info.eq_index, info.eq_type = _eq_at(raw, 41)
    info.eq_curve = GraphicEqCurve.from_inbound(raw[43:53])
    c = raw[63]
    base = 63 + c
    t = info.tail
    t["gesture_length"] = c
    try:
        t["mode_select_byte"] = raw[base - 1]
        t["colour_code"] = chr(raw[base]) if 32 <= raw[base] < 127 else raw[base]
        t["game_mode"] = raw[base + 1] != 0
        t["touch_tone"] = raw[base + 2] != 0
        t["auto_power_off_switch"] = raw[base + 3] != 0
        t["auto_power_off_index"] = raw[base + 4]
        info.partial = False
    except IndexError:
        info.partial = True
    return info


# --- a3936 (Space One, Style FIX, large HearID block) ---------------------

def parse_a3936(raw: bytes) -> DeviceInfo:
    info = parse_leading_blocks(raw, model="a3936")
    info.left_charging = raw[13] != 0
    info.right_charging = raw[14] != 0
    info.eq_index, info.eq_type = _eq_at(raw, 41)
    info.eq_curve = GraphicEqCurve.from_inbound(raw[43:53])
    t = info.tail
    t["hearid"] = {
        "age_profile_code": raw[63],
        "switch": raw[64] != 0,
        "type": raw[89],
        "eq_index": raw[110] | (raw[111] << 8),
        "time_be32": int.from_bytes(raw[85:89], "big"),
    }
    c = raw[112]
    t["gesture_length"] = c
    base = 112 + c
    try:
        t["mode_select"] = _mode_select(raw[base - 1])
        t["touch_tone"] = raw[base + 6] != 0
        t["case_battery"] = raw[base + 7]
        t["colour_code"] = chr(raw[base + 8]) if 32 <= raw[base + 8] < 127 else raw[base + 8]
        t["ldac"] = raw[base + 9] != 0
        t["dual_device_connection"] = raw[base + 10] != 0
        t["auto_power_off_switch"] = raw[base + 11] != 0
        t["auto_power_off_index"] = raw[base + 12]
        t["game_mode"] = raw[base + 13] != 0
        t["three_d_effect_mode"] = raw[base + 14]
        info.partial = False
    except IndexError:
        info.partial = True
    return info


# model code -> tail parser
TABULATED = {
    "a6610": parse_a6610,
    "a3040": parse_a3040,
    "a3994": parse_a3994,
    "a3936": parse_a3936,
}

# models known to use the TLV container
TLV_MODELS = frozenset(
    {"a3956", "d1105", "d1206", "d1302", "d1303", "d1406"}
)

# best-effort style guess for models we do not tabulate (DEVICE-INFO.md section 4)
BB_MODELS = frozenset(
    {
        "a3954",
        "a3957",
        "a3875",
        "d1200",
        "d1202",
        "d1205",
        "d5100",
        "d5103",
        "a31a3",
        "a3134",
        "a3138",
        "a3330",
        "a3331",
        "a3388",
        "d1101",
        "d3200",
    }
)
