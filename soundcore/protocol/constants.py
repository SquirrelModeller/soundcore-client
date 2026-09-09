"""Numeric constants and enums for the accessory protocol.

Values are observed protocol behaviour (see PROTOCOL.md / OPCODES.md). Names are
original to this project.
"""

from __future__ import annotations

from enum import IntEnum

# --- battery -----------------------------------------------------------------
BATTERY_MAX = 9  # coarse bar level, not a percentage (PROTOCOL.md section 7.3)


def clamp_battery(value: int) -> int:
    return max(0, min(BATTERY_MAX, value))


# --- EQ --------------------------------------------------------------------
EQ_BAND_HZ = (100, 200, 400, 800, 1600, 3200, 6400, 12800)  # graphic slots 0..7
EQ_SLOTS_PER_CHANNEL = 10  # slots 8..9 are carried but ~always 0
EQ_GAIN_SCALE = 10

# active-EQ-index sentinels: high byte of the LE16 index in the snapshot / eq_reply
EQ_INDEX_CUSTOM = 0xFE  # embedded 8-band curve is the source of truth
EQ_INDEX_NAMED_GROUP = 0xEE  # index = LE16 - 0xEE00, then remapped by a model table
EQ_INDEX_FORCE_2 = 0x7E  # index forced to 2
EQ_PRESET_INDEX_MAX = 21  # else: preset index = clamp(LE16, 0..21)


# --- feature groups (PROTOCOL.md section 6) --------------------------------
class Group(IntEnum):
    IDENTITY = 0x01
    EQ = 0x02
    HEARID = 0x03
    TOUCH = 0x04
    USER_DATA = 0x05
    AMBIENT = 0x06
    CHARGING_CASE = 0x07
    BOX_RECONNECT = 0x08
    WEAR_FIT = 0x09
    VOICE_ASSISTANT = 0x0A
    MULTI_DEVICE = 0x0B
    BELT_LIGHT = 0x0C
    GAMING = 0x0D
    LIGHTING = 0x0E
    USB_DONGLE = 0x0F
    SPATIAL_MISC = 0x10
    IMMERSIVE = 0x12
    SLEEP_SOUND = 0x13
    ALARM = 0x14
    SLEEP_QUALITY = 0x15
    PRESSURE = 0x16
    KARAOKE = 0x17
    TRANSLATION = 0x18
    MEDIA_VOICE = 0x19
    WIFI_CONFIG = 0x1A
    VIBRATION = 0x1B
    HEARING_PROTECTION = 0x20
    WIFI_INFO = 0x2A
    FUN_SWITCH = 0x41
    WALLPAPER = 0xFA
    DIAGNOSTICS = 0xFF


class AmbientMode(IntEnum):
    """0x06/0x81 `mode` byte. [confirm] against a capture -- the bitfield order in
    the snapshot (bit0 nc / bit1 transparency / bit2 normal) is firm, this standalone
    mapping is not."""

    NOISE_CANCELLING = 0
    TRANSPARENCY = 1
    NORMAL = 2  # out-of-range values clamp here


class TouchGesture(IntEnum):
    """`gesture` byte in key_down_report (0x04/0x8B). `side` (0 left / 1 right) is a
    separate byte."""

    DOUBLE = 0
    LONG_PRESS = 1
    SLIDE_UP = 3
    SLIDE_DOWN = 4


class Posture(IntEnum):
    """Bits of the parametric-EQ `ctx` byte and the standalone posture field."""

    STANDING = 0
    LAYING = 1
    HANGING = 2


# --- fun-switch / prompt-tone bit bank (groups 0x10 and 0x41) ---------------
# device -> host: [bit u8, value u8]. Short form is shared with group 0x10.
FUN_SWITCH_BITS_SHORT = {
    0: "touch_tone",
    1: "low_battery_alert",
    2: "power_off_tone",
    3: "in_ear_beep",
    4: "connect_tone",
    5: "mode_change_tone",
    6: "ambient_sound_notice",
}

# extended form (group 0x41)
FUN_SWITCH_BITS_EXTENDED = {
    0: "touch_lock",
    1: "game_mode",
    2: "ldac",
    3: "support_two_connections",
    4: "three_d_effect_mode",
    5: "bass_up",
    6: "adaptive_volume",
    7: "anc_switch",
    8: "wear_detection",
    9: "leak_compensation",
    10: "side_tone",
    11: "wind_noise_suppression",
    12: "adaptive_eq_enable",
    13: "hearid_switch",
    14: "easy_chat",
    15: "sleep_data",
    16: "auto_optimize_pressure",
    17: "spatial_switch",
    18: "large_noise_suppression",
    19: "voice_control",
    20: "super_audio",
    29: "sound_field_render",
    30: "hearing_health",
    32: "hear_guard",
    56: "enc_switch",
}
