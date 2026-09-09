from conftest import make_event_frame

from soundcore.deviceinfo import decode_eq_index, parse_device_info


def _snapshot(payload: bytes) -> bytes:
    return make_event_frame(0x01, 0x01, payload)


def test_decode_eq_index_sentinels():
    assert decode_eq_index(0xFE02) == (0x02, "custom")
    assert decode_eq_index(0x7E00) == (2, "force_2")
    assert decode_eq_index(0xEE05) == (0xEE05 - 0xEE00, "named_group")
    assert decode_eq_index(0x0003) == (3, "preset")
    assert decode_eq_index(0x00FF) == (21, "preset")  # clamped to EQ_PRESET_INDEX_MAX


def test_a6610_full_tail():
    p = bytearray(79)
    p[0] = 0            # host side
    p[1] = 1            # tws present
    p[2], p[3] = 5, 4   # batteries
    p[4], p[5] = 0, 1   # charging
    p[6:11] = b"01.20"
    p[11:16] = b"01.20"
    p[16:32] = b"ABCDEF0123456789"
    p[32], p[33] = 0x02, 0xFE          # eq index -> custom
    p[34:44] = bytes([160] + [120] * 9)  # curve: slot0 = +4 dB
    p[66] = 0b0000_0101                 # mode-select: nc + normal
    p[67] = 1                           # current mode
    p[68] = 1                           # smart play/pause
    p[69] = 30                          # custom play time
    p[70] = 1                           # adaptive nc
    p[71] = 1                           # voice prompt
    p[72] = ord("A")                    # colour code
    p[73], p[74], p[75] = 2, 1, 5      # sleep sound id/present/volume
    p[76] = 3                           # press sensitivity (frame >= 87)
    p[77], p[78] = 0x00, 0x1E          # play-countdown BE16 = 30 (frame >= 89)

    info = parse_device_info(_snapshot(bytes(p)), model="a6610")
    assert info.partial is False
    assert info.style == "FIX"
    assert (info.left_battery, info.right_battery) == (5, 4)
    assert (info.left_charging, info.right_charging) == (False, True)
    assert info.left_firmware == "01.20"
    assert info.serial == "ABCDEF0123456789"
    assert info.eq_type == "custom"
    assert info.eq_curve is not None
    assert info.eq_curve.left[0] == 4.0
    mode_select = info.tail["mode_select"]
    assert isinstance(mode_select, dict)
    assert mode_select["nc_selected"] is True
    assert mode_select["transp_selected"] is False
    assert info.tail["current_mode"] == 1
    assert info.tail["colour_code"] == "A"
    assert info.tail["press_sensitivity"] == 3
    assert info.tail["play_countdown_minutes"] == 30


def test_unknown_model_falls_back_to_leading_blocks():
    p = bytearray(40)
    p[0], p[1] = 0, 1
    p[2], p[3] = 7, 6
    p[4], p[5] = 1, 0
    p[6:11] = b"09.99"
    p[11:16] = b"09.99"
    p[16:32] = b"SERIALSERIAL1234"
    info = parse_device_info(_snapshot(bytes(p)), model="a9999")
    assert info.partial is True
    assert info.left_battery == 7 and info.right_battery == 6
    assert info.left_charging is True
    assert info.serial == "SERIALSERIAL1234"


def test_aerofit_open_earbud_skips_charging_bytes():
    p = bytearray(40)
    p[0], p[1] = 0, 1
    p[2], p[3] = 8, 8
    p[4:9] = b"AA.BB"        # frame off 13.. is firmware, not charging
    p[9:14] = b"AA.BB"
    p[14:30] = b"0123456789ABCDEF"
    info = parse_device_info(_snapshot(bytes(p)), model="a3875")
    assert info.left_charging is None  # not present in this layout
    assert info.left_firmware == "AA.BB"
    assert info.serial == "0123456789ABCDEF"


def test_tlv_container_common_tags():
    body = bytearray()
    body += bytes([0x01, 1, 0])               # host side
    body += bytes([0x02, 1, 1])               # tws present
    body += bytes([0x03, 2, 1, 5])            # left: charging, battery
    body += bytes([0x04, 2, 0, 4])            # right
    body += bytes([0x07, 16]) + b"TLVSERIAL00000AB"
    body += bytes([0x0B, 2, 0x00, 0xFE])      # eq index -> custom
    body += bytes([0x0C, 10]) + bytes([160] + [120] * 9)
    body += bytes([0x99, 3, 1, 2, 3])         # unknown tag -> collected

    info = parse_device_info(_snapshot(bytes(body)), model="a3956")
    assert info.style == "TLV"
    assert info.left_battery == 5 and info.right_battery == 4
    assert info.left_charging is True and info.right_charging is False
    assert info.serial == "TLVSERIAL00000AB"
    assert info.eq_type == "custom"
    assert info.eq_curve is not None
    assert info.eq_curve.left[0] == 4.0
    assert info.tail["tags"] == {0x99: "010203"}


def test_tlv_autodetected_without_model():
    body = bytes([0x01, 1, 0, 0x02, 1, 1, 0x07, 4]) + b"S123"
    info = parse_device_info(_snapshot(body))
    assert info.style == "TLV"
    assert info.serial == "S123"
