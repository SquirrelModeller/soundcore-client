import inspect

import pytest

from soundcore import AmbientMode, Commands, GraphicEqCurve, ParametricEqCurve
from soundcore.commands import COMMAND_NAMES
from soundcore.protocol import checksum


def _opcode(frame: bytes) -> tuple[int, int]:
    return frame[5], frame[6]


def _payload(frame: bytes) -> bytes:
    return frame[9:-1]


def _dummy_for(param: inspect.Parameter):
    # `from __future__ import annotations` makes these strings
    ann = str(param.annotation)
    if ann == "bool":
        return True
    if ann == "str":
        return "AA:BB:CC:DD:EE:FF"
    if ann == "bytes":
        return b"\x00\x00"
    if "GraphicEqCurve" in ann:
        return GraphicEqCurve(left=[1.0])
    if "ParametricEqCurve" in ann:
        return ParametricEqCurve(points=[])
    if ann.startswith("list"):
        return [1, 2]
    return 1  # int and everything else


def test_every_command_builds_a_valid_frame():
    """Call every builder with type-appropriate dummy args; assert frame invariants."""
    for name in COMMAND_NAMES:
        fn = getattr(Commands, name)
        sig = inspect.signature(fn)
        args = [
            _dummy_for(p)
            for p in sig.parameters.values()
            if p.default is inspect.Parameter.empty and p.kind is not p.VAR_POSITIONAL
        ]
        frame = fn(*args)
        assert frame[:4] == bytes([0x08, 0xEE, 0x00, 0x00]), name
        assert frame[-1] == checksum(frame[:-1]), name
        assert (frame[7] | (frame[8] << 8)) == len(frame), name


def test_command_surface_size():
    # ~185 named builders across the checksummed stack
    assert len(COMMAND_NAMES) > 170


def test_request_device_info_is_empty_payload():
    f = Commands.request_device_info()
    assert _opcode(f) == (0x01, 0x01)
    assert _payload(f) == b""


def test_set_volume_single_byte():
    f = Commands.set_volume(12)
    assert _opcode(f) == (0x01, 0x88)
    assert _payload(f) == bytes([12])


def test_set_ambient_mode_4byte_and_clamps():
    f = Commands.set_ambient_mode(
        AmbientMode.NOISE_CANCELLING, nc_level=9, transparency_level=9, custom_nc=99
    )
    assert _opcode(f) == (0x06, 0x81)
    assert _payload(f) == bytes([0, 3, 2, 10])  # clamped
    f2 = Commands.set_ambient_mode(7)  # out-of-range mode -> NORMAL
    assert _payload(f2)[0] == 2


def test_set_ambient_mode_extended_is_7_bytes_with_nibble_packing():
    f = Commands.set_ambient_mode_extended(1, 2, 0, 0xA, 0xB, 0xC, 0xD, 4, 5)
    p = _payload(f)
    assert len(p) == 7
    assert p[3] == ((0xA << 4) | 0xB)
    assert p[4] == ((0xC << 4) | 0xD)


def test_set_eq_preset_is_index_plus_20():
    from soundcore import GraphicEqCurve

    f = Commands.set_eq_preset(0xFEFE, GraphicEqCurve(left=[4.0]))
    p = _payload(f)
    assert _opcode(f) == (0x02, 0x81)
    assert p[:2] == bytes([0xFE, 0xFE])  # LE16 index
    assert len(p) == 22
    assert p[2] == 0x28  # first slot +4 dB


def test_wind_suppression_writes_inverted_boolean():
    assert _payload(Commands.set_wind_suppression(True)) == bytes([0])
    assert _payload(Commands.set_wind_suppression(False)) == bytes([1])


def test_touch_action_enable_polarity_is_inverted():
    on = _payload(Commands.set_touch_action(3, 1, 2, enable=True))
    off = _payload(Commands.set_touch_action(3, 1, 2, enable=False))
    assert on[0] == 0 and off[0] == 1
    assert on[2] == ((1 << 4) | 2)


def test_set_touch_gesture_slot_array():
    p = _payload(Commands.set_touch_gesture(2, 0x09))
    assert p == bytes([0xFF, 0xFF, 0x09, 0xFF, 0xFF, 0xFF])


def test_sync_time_endianness_toggle():
    le = _payload(Commands.sync_time(0x01020304))
    be = _payload(Commands.sync_time(0x01020304, big_endian=True))
    assert le == bytes([0x04, 0x03, 0x02, 0x01])
    assert be == bytes([0x01, 0x02, 0x03, 0x04])
    assert _payload(Commands.sync_time(0, tz_byte=5))[-1] == 5


def test_set_alarm_7_and_8_bytes():
    assert len(_payload(Commands.set_alarm(1, True, 480, 0x7F, 2, 5))) == 7
    assert len(_payload(Commands.set_alarm(1, True, 480, 0x7F, 2, 5, snooze_minutes=9))) == 8
    p = _payload(Commands.set_alarm(1, True, 480, 0, 0, 0))
    assert p[2] == (480 & 0xFF) and p[3] == (480 >> 8)  # minute low then high


def test_gaming_mode_is_9_bytes_le16_fields():
    p = _payload(Commands.set_gaming_mode(True, 1, 0x1234, 0x5678, 0x9ABC, 0xDE))
    assert len(p) == 9
    assert p[2:4] == bytes([0x34, 0x12])
    assert p[4:6] == bytes([0x78, 0x56])


def test_mac_helpers_reject_bad_length():
    with pytest.raises(ValueError):
        Commands.connect_mac_device("AA:BB:CC")
    f = Commands.connect_mac_device("AA:BB:CC:DD:EE:FF")
    assert _payload(f) == bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF])


def test_raw_escape_hatch_and_route_override():
    f = Commands.raw(0x99, 0x01, b"\x01\x02", route=0x10)
    assert f[4] == 0x10 and _opcode(f) == (0x99, 0x01)


def test_command_names_populated():
    assert "set_volume" in COMMAND_NAMES
    assert "set_eq_preset" in COMMAND_NAMES
    assert "raw" not in COMMAND_NAMES
