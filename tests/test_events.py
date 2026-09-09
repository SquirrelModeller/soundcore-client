from conftest import make_event_frame

from soundcore.events import parse_event
from soundcore.protocol import parse_frame


def _ev(group, command, payload=b""):
    return parse_event(parse_frame(make_event_frame(group, command, payload)))


def test_battery_changed():
    e = _ev(0x01, 0x03, bytes([5, 4, 3, 0]))
    assert e.name == "battery_changed"
    assert e.fields == {"left_battery": 5, "right_battery": 4, "case_battery": 3}


def test_battery_clamped_to_bar_level():
    e = _ev(0x01, 0x03, bytes([200, 0, 99, 0]))
    assert e.fields["left_battery"] == 9 and e.fields["case_battery"] == 9


def test_charging_changed():
    e = _ev(0x01, 0x04, bytes([1, 0, 0]))
    assert e.fields == {"left_charging": True, "right_charging": False}


def test_eq_reply_sentinel_and_biased_curve():
    payload = bytes([0x00, 0xFE, 0x01, 160]) + bytes([120] * 9)
    e = _ev(0x02, 0x01, payload)
    assert e.name == "eq_reply"
    assert e.fields["eq_type"] == "custom"
    assert e.fields["eq_index"] == 0xFE00
    assert e.fields["hearid5_switch"] is True
    assert e.fields["curve"].left[0] == 4.0  # decoded with the read-side rule
    assert e.fields["curve"].left[1] == 0.0


def test_ambient_details_reply():
    e = _ev(0x06, 0x01, bytes([1, 2, 1, 0xFF]))
    assert e.fields == {"option": 1, "anc_option": 2, "transparency_option": 1, "custom_anc": 0xFF}


def test_custom_btn_anc_selected_bitfield():
    e = _ev(0x06, 0x02, bytes([0b0000_0101, 0, 0]))
    assert e.fields["nc_selected"] and e.fields["normal_selected"]
    assert not e.fields["transp_selected"]


def test_key_down_report():
    e = _ev(0x04, 0x8B, bytes([1, 4]))
    assert e.fields == {"side": 1, "gesture": 4}


def test_fun_switch_reply_names_the_bit():
    e = _ev(0x41, 0x88, bytes([10, 1]))
    assert e.fields["name_extended"] == "side_tone"
    assert e.fields["value"] == 1


def test_alarm_list_reply_records():
    rec = bytes([1, 1, 0xE0, 0x01, 3, 5, 0x7F])  # minute_of_day 0x01E0 = 480
    e = _ev(0x14, 0x01, rec + rec)
    assert len(e.fields["alarms"]) == 2
    assert e.fields["alarms"][0]["minute_of_day"] == 480
    assert e.fields["alarms"][0]["repeat_mask"] == 0x7F


def test_hearing_health_avg_reply_shape():
    payload = bytes(80)
    e = _ev(0x20, 0x05, payload)
    assert "current_round" in e.fields and "last_round" in e.fields
    assert len(e.fields["current_round"]["in_ear_exposure_time"]) == 5


def test_wifi_info_changed_dotted_quad():
    e = _ev(0x2A, 0x01, bytes([10, 0, 0, 42, 0x50, 0x00]))
    assert e.fields["ip"] == "42.0.0.10"
    assert e.fields["port"] == 0x50


def test_unknown_set_reply_is_bare_ack():
    e = _ev(0x01, 0x81, bytes([1]))
    assert e.bare_ack is True
    assert e.name == "ack_01_81"


def test_unknown_non_reply_is_generic_event():
    e = _ev(0x0D, 0x01, bytes([1, 2, 3, 4, 5]))
    assert e.bare_ack is False
    assert e.name == "event_0d_01"


def test_truncated_payload_surfaces_parse_error_not_crash():
    e = _ev(0x20, 0x05, bytes([1, 2]))  # far too short for the avg parser
    assert "parse_error" in e.fields
