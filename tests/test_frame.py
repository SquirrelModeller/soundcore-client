from conftest import make_event_frame

from soundcore.protocol import build_command, checksum, route_for, split_events
from soundcore.protocol.frame import FRAMING_LEGACY, parse_frame


def test_command_frame_structure():
    payload = bytes([0x00, 0x02, 0x00, 0xFF])
    frame = build_command(0x06, 0x81, payload)
    assert frame[:5] == bytes([0x08, 0xEE, 0x00, 0x00, 0x00])  # prefix + route 0x00
    assert frame[5] == 0x06 and frame[6] == 0x81
    total = frame[7] | (frame[8] << 8)
    assert total == len(frame) == 10 + len(payload)
    assert frame[9:-1] == payload
    assert frame[-1] == checksum(frame[:-1])


def test_empty_payload_length_is_ten():
    frame = build_command(0x01, 0x01)
    assert (frame[7] | (frame[8] << 8)) == 10
    assert len(frame) == 10


def test_route_byte_rule():
    assert route_for(0x07, 0x8B) == 0x00
    for c in range(0x8C, 0x91):
        assert route_for(0x07, c) == 0x10
    assert route_for(0x07, 0x91) == 0x00
    assert route_for(0x06, 0x81) == 0x00
    assert build_command(0x07, 0x8D)[4] == 0x10
    assert build_command(0x07, 0x8B)[4] == 0x00


def test_legacy_framing_has_no_checksum_byte():
    payload = bytes([1, 2, 3])
    frame = build_command(0x06, 0x81, payload, framing=FRAMING_LEGACY)
    assert (frame[7] | (frame[8] << 8)) == 9 + len(payload)
    assert len(frame) == 9 + len(payload)  # no trailing checksum
    assert frame[9:] == payload


def test_split_events_roundtrip_and_remainder():
    a = make_event_frame(0x01, 0x03, bytes([5, 4, 3, 0]))
    b = make_event_frame(0x02, 0x01, bytes([0x00, 0xFE, 0x01]))
    frames, rest = split_events(a + b + b[:4])
    assert rest == b[:4]
    assert [(f.group, f.command) for f in frames] == [(0x01, 0x03), (0x02, 0x01)]
    assert all(f.checksum_ok for f in frames)


def test_split_events_resyncs_on_garbage():
    good = make_event_frame(0x01, 0x03, bytes([1, 2, 3, 0]))
    frames, rest = split_events(b"\x00\x11\x22" + good)
    assert len(frames) == 1 and frames[0].group == 0x01
    assert rest == b""


def test_bad_checksum_flagged():
    good = bytearray(make_event_frame(0x01, 0x03, bytes([1, 2, 3, 0])))
    good[-1] ^= 0xFF
    f = parse_frame(bytes(good))
    assert f.checksum_ok is False


def test_device_info_reply_is_not_flagged_as_reply():
    f = parse_frame(make_event_frame(0x01, 0x01, b"\x00" * 30))
    assert f.is_reply is False  # high bit clear -- request code reused
    g = parse_frame(make_event_frame(0x01, 0x83, b"\x00"))
    assert g.is_reply is True
