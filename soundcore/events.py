"""Device -> host event parsing (EVENTS.md).

`parse_event(frame)` returns a `ParsedEvent`: a stable name, the decoded fields,
and whether it looked like a bare acknowledgement (a `set_*` reply with no payload
fields). Opcodes without a dedicated parser still come back with `fields={"raw": ...}`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .protocol import (
    FUN_SWITCH_BITS_EXTENDED,
    FUN_SWITCH_BITS_SHORT,
    Frame,
    GraphicEqCurve,
    clamp_battery,
)


@dataclass
class ParsedEvent:
    name: str
    group: int
    command: int
    fields: dict[str, Any]  # decoded payload; a loose bag by design
    frame: Frame
    bare_ack: bool = False

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<ParsedEvent {self.name} g=0x{self.group:02X} c=0x{self.command:02X} {self.fields}>"


# --- little helpers -------------------------------------------------------
def _u8(p: bytes, off: int) -> int:
    return p[off]


def _bool(p: bytes, off: int) -> bool:
    return p[off] != 0


def _le16(p: bytes, off: int) -> int:
    return p[off] | (p[off + 1] << 8)


def _be16(p: bytes, off: int) -> int:
    return (p[off] << 8) | p[off + 1]


def _le32(p: bytes, off: int) -> int:
    return int.from_bytes(p[off : off + 4], "little")


def _le64(p: bytes, off: int) -> int:
    return int.from_bytes(p[off : off + 8], "little")


def _ascii(p: bytes, start: int, length: int) -> str:
    return p[start : start + length].decode("ascii", "replace")


# --- individual parsers -------------------------------------------------
# each takes the payload (offset 0 == frame offset 9) and returns a dict


def _battery(p):
    return {
        "left_battery": clamp_battery(p[0]),
        "right_battery": clamp_battery(p[1]),
        "case_battery": clamp_battery(p[2]),
    }


def _charging(p):
    return {"left_charging": _bool(p, 0), "right_charging": _bool(p, 1)}


def _tws_state(p):
    return {"host_side": p[0], "tws_present": _bool(p, 1)}


def _ear_form(p):
    return {"current_form": p[0], "left_form": p[1], "right_form": p[2]}


def _device_storage(p):
    return {"used_bytes": _le32(p, 0), "total_bytes": _le32(p, 4)}


def _query_device_status(p):
    return {"left_wear": p[0], "right_wear": p[1]}


def _single_value(p):
    return {"value": p[0] if p else None}


def _single_bool(p):
    return {"value": _bool(p, 0) if p else None}


def _eq_reply(p):
    index = _le16(p, 0)
    hi = p[1]
    if hi == 0xFE:
        eq_type = "custom"
    elif hi == 0xEE:
        eq_type = "named_group"
    elif hi == 0x7E:
        eq_type = "force_2"
    else:
        eq_type = "preset"
    out: dict[str, object] = {"eq_index": index, "eq_type": eq_type}
    if len(p) >= 4:
        out["hearid5_switch"] = _bool(p, 2)
    if len(p) >= 13:
        # inbound curve is the biased/unsigned encoding -- decode with read_gain_db,
        # never echo these bytes into a set command. Exact start offset (2 vs 3) and
        # clamp bounds are [confirm] (EVENTS.md open item 1); this takes offset 3.
        out["curve"] = GraphicEqCurve.from_inbound(p[3:13])
    return out


def _hearid_switch(p):
    return {"hearid_switch": p[1] == 1}  # note offset 1, not 0


def _personal_nc_result(p):
    out = {"result_index": p[0]}
    if len(p) >= 43:
        out["test_result"] = p[0:42].hex()
    return out


def _hearid3_result(p):
    out = {
        "timestamp": _le32(p, 0),
        "left_ear_data": list(p[4:14]),
        "right_ear_data": list(p[14:24]),
        "age_range_index": p[24],
        "gender": p[25],
        "level": p[26],
        "noise_interference": _bool(p, 27),
        "seal_fail": _bool(p, 28),
        "large_hearing_variation": _bool(p, 29),
    }
    if len(p) >= 51:
        out["left_ear_nl2_data"] = list(p[30:40])
        out["right_ear_nl2_data"] = list(p[40:50])
    return out


def _key_down_report(p):
    return {"side": p[0], "gesture": p[1]}


def _ambient_details(p):
    return {
        "option": p[0],
        "anc_option": p[1],
        "transparency_option": p[2],
        "custom_anc": p[3],
    }


def _custom_btn_anc_selected(p):
    b = p[0]
    return {
        "nc_selected": bool(b & 0x01),
        "transp_selected": bool(b & 0x02),
        "normal_selected": bool(b & 0x04),
        "un_tws_nc_selected": bool(b & 0x08),
        "un_tws_transp_selected": bool(b & 0x10),
        "un_tws_normal_selected": bool(b & 0x20),
        "raw": b,
    }


def _charging_box_display(p):
    out = {
        "remote_camera": _bool(p, 0),
        "find_device": _bool(p, 1),
        "spatial_audio": _bool(p, 2),
    }
    if len(p) >= 5:
        out["barometer"] = _bool(p, 3)
    return out


def _ears_in_case(p):
    return {"left_in_case": _bool(p, 0), "right_in_case": _bool(p, 1)}


def _wear_fit(p):
    out = {"left_fit_code": p[0], "right_fit_code": p[1]}
    if len(p) >= 15:
        out.update(
            left_pressure=_le16(p, 2),
            right_pressure=_le16(p, 4),
            left_high_over=_le16(p, 6),
            right_high_over=_le16(p, 8),
            left_low_over=_le16(p, 10),
            right_low_over=_le16(p, 12),
        )
    return out


def _wear_status(p):
    return {"left_wearing": _bool(p, 0), "right_wearing": _bool(p, 1)}


def _connect_history(p):
    out = {"total_package": p[0], "cur_package": p[1], "records": []}
    # records start at frame offset 11 == payload offset 2, length-prefixed
    i = 2
    while i < len(p):
        rec_len = p[i]
        if rec_len <= 8 or i + rec_len > len(p):
            break
        status = p[i + 1]
        mac = p[i + 2 : i + 8].hex(":")
        name = _ascii(p, i + 8, rec_len - 8)
        out["records"].append({"status": status, "mac": mac, "name": name})
        i += rec_len
    return out


def _dual_device_audio_focus(p):
    out = {"focus": p[0]}
    if p[0] != 0 and len(p) >= 7:
        out["mac"] = p[1:7].hex(":")
    return out


def _device_connect_mode(p):
    mode = p[0]
    return {"mode": mode, "multi_device_play_mode": mode ^ 1}


def _heart_rate(p):
    return {"heart_rate": p[0]}


def _light_effect_report(p):
    length, index, count = p[0], p[1], p[2]
    colours = []
    off = 3
    for _ in range(count):
        if off + 3 > len(p):
            break
        colours.append((p[off], p[off + 1], p[off + 2]))
        off += 3
    return {"length": length, "index": index, "count": count, "colours": colours}


def _single_light_color(p):
    return {"rgb": (p[0], p[1], p[2])}


def _preset_eq_light(p):
    return {"colours": [(p[0], p[1], p[2]), (p[6], p[7], p[8]), (p[12], p[13], p[14])]}


def _sports_timing_exit(p):
    return {"mode": p[0], "state": p[1]}


def _sports_timing_memory(p):
    # duration: raw LE16. The vendor helper sign-extends the hi byte (bug for hi>=0x80).
    return {"mode": p[0], "duration": _le16(p, 1)}


def _dongle_info(p):
    count = p[0]
    records = []
    off = 1
    for _ in range(count):
        if off + 33 > len(p):
            break
        rec = p[off : off + 33]
        records.append(
            {
                "name": rec[0:20].decode("ascii", "replace").rstrip("\x00"),
                "type": rec[20],
                "device_id": rec[21],
                "firmware": rec[22:27].decode("ascii", "replace"),
                "mac": rec[27:33].hex(":"),
            }
        )
        off += 33
    return {"count": count, "records": records}


def _spatial_audio(p):
    return {"switch": _bool(p, 0), "effect_mode": p[1], "sound_mode": p[2]}


def _find_device_state(p):
    return {"left_finding": _bool(p, 0), "right_finding": _bool(p, 1), "case_finding": _bool(p, 2)}


def _ldac_state_tws(p):
    return {"ldac": _bool(p, 0), "tws_ldac_enable": _bool(p, 1)}


def _in_ear_calibrate(p):
    return {
        "start": _bool(p, 0),
        "in_ear_hr_state": p[1],
        "in_ear_wear_state": p[2],
        "in_ear_head_state": p[3],
    }


def _immersive_status(p):
    return {"mode": p[0]}


def _sound_list(p):
    count = p[0]
    items = []
    off = 1
    for _ in range(count):
        if off + 10 > len(p):
            break
        items.append(
            {
                "index": p[off],
                "transfer_id": _le64(p, off + 1),
                "play_type": p[off + 9] or 2,
            }
        )
        off += 10
    out = {"count": count, "items": items}
    if off + 1 < len(p):
        out["selected_index"] = p[off]
        out["playback_status"] = p[off + 1]
    return out


def _current_sound(p):
    return {
        "index": p[0],
        "sound_id": _le64(p, 1),
        "playing": _bool(p, 9),
        "volume": p[10],
    }


def _alarm_list(p):
    alarms = []
    off = 0
    while off + 7 <= len(p):
        alarms.append(
            {
                "id": p[off],
                "enabled": p[off + 1] == 1,
                "minute_of_day": _le16(p, off + 2),
                "sound_id": p[off + 4],
                "volume": p[off + 5],
                "repeat_mask": p[off + 6],
            }
        )
        off += 7
    return {"alarms": alarms}


def _next_alarm(p):
    if p[0] == 0xFF:
        return {"id": 0xFF, "present": False}
    return {
        "id": p[0],
        "present": True,
        "enabled": p[1] == 1,
        "minute_of_day": _le16(p, 2),
        "repeat_mask": p[4],
        "sound_id": p[5],
        "volume": p[6],
    }


def _one_use_alarm(p):
    return {"open": _bool(p, 0), "minute_of_day": _le16(p, 1), "sound_id": p[3]}


def _sleep_cycle_alarm_list(p):
    # NB: the vendor parser starts this one at frame offset 12 == payload offset 3
    alarms = []
    off = 3
    while off + 16 <= len(p):
        if p[off + 1] != 0xFF:
            alarms.append(
                {
                    "id": p[off],
                    "enabled": p[off + 1],
                    "wakeup_minute": _le16(p, off + 2),
                    "repeat_mask": p[off + 4],
                    "sound_id": p[off + 5],
                    "volume": p[off + 6],
                    "snooze_minutes": p[off + 7],
                    "bedtime_minute": _le16(p, off + 8),
                    "sleep_reminder_minutes": p[off + 10],
                    "sleep_reminder_switch": p[off + 11],
                    "one_time_end_timestamp": _le32(p, off + 12),
                }
            )
        off += 16
    return {"alarms": alarms}


def _shut_off_data(p):
    return {
        "shut_off_mode": p[0],
        "fall_asleep_time": _le16(p, 1),
        "switch_to_sleep_mode": _bool(p, 3),
    }


def _pressure_info(p):
    return {"pressure": p[0], "optimize_status": _bool(p, 1)}


def _stage_reverb(p):
    return {"index": p[0], "intensity": p[1]}


def _mic_list(p):
    count = p[0]
    mics = []
    off = 1
    for _ in range(count):
        if off + 3 > len(p):
            break
        mics.append({"index": p[off], "type": p[off + 1], "battery": p[off + 2]})
        off += 3
    return {"count": count, "mics": mics}


def _audio_record_cmd(p):
    return {"start_audio_record": p[0] in (1, 2), "raw": p[0]}


def _inverted_enable(p):
    return {"enabled": p[0] == 0}


def _emergency_sound(p):
    return {"sound_id": p[0], "sound_play_time": p[1], "play_status": p[2]}


def _wear_check(p):
    return {"wear": _bool(p, 0), "wear_level": _le16(p, 1)}


def _hearing_health_realtime(p):
    return {"left_db": p[0], "right_db": p[1]}


def _round_data(p, base):
    return {
        "wear_time": _le16(p, base),
        "protection_time": _le16(p, base + 2),
        "avg_in_ear_vol": p[base + 4],
        "min_in_ear_vol": p[base + 5],
        "max_in_ear_vol": p[base + 6],
        "in_ear_exposure_time": [_le16(p, base + 7 + 2 * k) for k in range(5)],
        "avg_ambient_vol": p[base + 17],
        "min_ambient_vol": p[base + 18],
        "max_ambient_vol": p[base + 19],
        "ambient_exposure_time": [_le16(p, base + 20 + 2 * k) for k in range(5)],
    }


def _hearing_health_avg(p):
    return {
        "total_wear_time_h": _le16(p, 0),
        "total_listening_time_h": _le16(p, 2),
        "total_protection_time_h": _le16(p, 4),
        "current_round": _round_data(p, 6),
        "last_round": _round_data(p, 36),
        "hearing_score": p[66],
        "hearing_score_last": p[67],
        "report_count": p[68],
    }


def _wifi_info_changed(p):
    ip = f"{p[3]}.{p[2]}.{p[1]}.{p[0]}"
    return {"ip": ip, "port": _le16(p, 4)}


def _fun_switch(p):
    bit, value = p[0], p[1]
    return {
        "bit": bit,
        "value": value,
        "name_short": FUN_SWITCH_BITS_SHORT.get(bit),
        "name_extended": FUN_SWITCH_BITS_EXTENDED.get(bit),
    }


def _ir_sensor(p):
    if len(p) < 24:
        return {
            "left_ir": _le16(p, 0),
            "right_ir": _le16(p, 2),
            "left_p": _le16(p, 4),
            "right_p": _le16(p, 6),
        }
    return {"register_dump": p.hex()}


def _hex_blob(p):
    return {"hex": p.hex()}


def _emergency_reply_stub(p):
    return {"raw": p.hex()}


# --- registry --------------------------------------------------------------
# (group, command) -> (event name, parser)
_Parser = Callable[[bytes], Mapping[str, object]]
_PARSERS: dict[tuple[int, int], tuple[str, _Parser]] = {
    (0x01, 0x03): ("battery_changed", _battery),
    (0x01, 0x04): ("charging_changed", _charging),
    (0x01, 0x02): ("tws_state_reply", _tws_state),
    (0x01, 0x10): ("ear_form_reply", _ear_form),
    (0x01, 0xB6): ("device_storage_reply", _device_storage),
    (0x01, 0xB7): (
        "device_indicator_status_reply",
        lambda p: {"pickup_status": p[0], "charging_compartment_status": p[1]},
    ),
    (0x01, 0xBC): ("query_device_status_reply", _query_device_status),
    (0x01, 0x7F): ("sound_quality_reply", _single_value),
    (0x01, 0x12): ("super_hearing_reply", _single_bool),
    (0x01, 0x11): ("game_switch_reply", _single_bool),
    (0x01, 0x36): ("party_cast_reply", _single_bool),
    (0x01, 0x33): ("play_status_reply", _single_bool),
    (0x01, 0x15): ("play_pause_reply", _single_bool),
    (0x01, 0x14): ("cur_mode_reply", _single_value),
    (0x01, 0x09): ("volume_reply", _single_value),
    (0x01, 0x8B): ("sound_source_reply", _single_value),
    (0x01, 0x83): ("app_music_stop_reply", _single_value),
    (0x02, 0x01): ("eq_reply", _eq_reply),
    (0x02, 0x8C): ("adaptive_eq_direction_reply", _single_value),
    (0x02, 0x8E): ("valid_eq_index_reply", _single_value),
    (0x02, 0x8F): ("eq_index_report_reply", _single_value),
    (0x02, 0x06): ("three_d_effect_reply", _single_bool),
    (0x03, 0x81): ("hearid_switch_reply", _hearid_switch),
    (0x03, 0x88): ("personal_nc_result", _personal_nc_result),
    (0x03, 0x89): ("personal_nc_reset_reply", lambda p: {"result_index": 255}),
    (0x03, 0x91): ("personal_nc_switch_reply", _single_bool),
    (0x03, 0x94): ("hearid3_result_reply", _hearid3_result),
    (0x04, 0x8B): ("key_down_report", _key_down_report),
    (0x06, 0x01): ("ambient_details_reply", _ambient_details),
    (0x06, 0x02): ("custom_btn_anc_selected_reply", _custom_btn_anc_selected),
    (0x06, 0x07): ("ambient_switch_reply", _single_bool),
    (0x06, 0x08): ("smart_nc_switch_reply", _single_bool),
    (0x07, 0x02): ("ears_in_case_reply", _ears_in_case),
    (0x07, 0x07): ("charging_box_display_reply", _charging_box_display),
    (0x07, 0x04): ("charging_box_connected_reply", _single_bool),
    (0x07, 0x05): ("ota_enable_reply", _single_value),
    (0x07, 0x09): ("box_guide_status_reply", _single_bool),
    (0x07, 0x89): ("prepare_box_ota_reply", _single_bool),
    (0x08, 0x03): ("box_reconn", _emergency_reply_stub),
    (0x09, 0x01): ("wear_fit_reply", _wear_fit),
    (0x09, 0x02): ("wear_status_reply", _wear_status),
    (0x0B, 0x01): ("connect_history_reply", _connect_history),
    (0x0B, 0x02): ("dual_device_audio_focus_reply", _dual_device_audio_focus),
    (0x0B, 0x05): ("connect_device_max_reply", _single_value),
    (0x0B, 0x07): ("device_connect_mode_reply", _device_connect_mode),
    (0x0B, 0x03): ("connected_device_count_reply", _single_value),
    (0x0D, 0x88): ("heart_rate_changed", _heart_rate),
    (0x0E, 0x04): ("light_effect_report", _light_effect_report),
    (0x0E, 0x06): ("brightness_value_reply", _single_value),
    (0x0E, 0x09): ("brightness_switch_reply", _single_bool),
    (0x0E, 0x0E): ("single_light_color_reply", _single_light_color),
    (0x0E, 0x0F): ("light_effect_switch_reply", lambda p: {"switch": p[0] == 1}),
    (0x0E, 0x10): ("preset_eq_light_reply", _preset_eq_light),
    (0x0E, 0x13): ("light_mode_random_color_reply", _single_value),
    (0x0E, 0x8F): ("sports_timing_exit_report", _sports_timing_exit),
    (0x0E, 0x90): ("sports_timing_memory_report", _sports_timing_memory),
    (0x0F, 0x01): ("dongle_info_reply", _dongle_info),
    (0x0F, 0x02): ("dongle_lpwr_switch_reply", _single_bool),
    (0x10, 0x01): ("spatial_audio_reply", _spatial_audio),
    (0x10, 0x09): ("find_device_state_reply", _find_device_state),
    (0x10, 0x8A): ("ldac_state_tws_reply", _ldac_state_tws),
    (0x10, 0x84): ("in_ear_calibrate_reply", _in_ear_calibrate),
    (0x10, 0x5A): ("speaker_tws_status_reply", _single_bool),
    (0x10, 0x93): ("button_brightness_reply", _single_value),
    (0x10, 0x91): ("stamina_switch_reply", _single_bool),
    (0x10, 0x70): ("auracast_switch_reply", _single_bool),
    (0x10, 0x7A): ("env_sound_detect_reply", _single_bool),
    (0x10, 0x03): ("easy_chat_switch_reply", _single_bool),
    (0x10, 0x61): ("nap_switch_reply", _single_bool),
    (0x10, 0x7B): ("nap_mode_reply", _single_bool),
    (0x10, 0x8D): ("smart_talk_status_reply", _single_bool),
    (0x12, 0x01): ("immersive_status_reply", _immersive_status),
    (0x13, 0x01): ("sound_list_reply", _sound_list),
    (0x13, 0x03): ("current_sound_reply", _current_sound),
    (0x14, 0x01): ("alarm_list_reply", _alarm_list),
    (0x14, 0x02): ("next_alarm_reply", _next_alarm),
    (0x14, 0x85): ("one_use_alarm_reply", _one_use_alarm),
    (0x14, 0x86): ("one_use_alarm_status_reply", _single_value),
    (0x14, 0x83): ("app_music_stop_reply", _single_value),
    (0x14, 0x89): ("sleep_cycle_alarm_list_reply", _sleep_cycle_alarm_list),
    (0x15, 0x03): ("shut_off_data_reply", _shut_off_data),
    (0x15, 0x07): ("smart_switch_sound_index_reply", _single_value),
    (0x16, 0x01): ("pressure_info_reply", _pressure_info),
    (0x17, 0x02): ("stage_reverb_reply", _stage_reverb),
    (0x17, 0x04): ("voice_modification_reply", _single_value),
    (0x17, 0x06): ("accompaniment_mode_reply", _single_value),
    (0x17, 0x08): ("accompaniment_volume_reply", _single_value),
    (0x17, 0x09): ("mic_list_reply", _mic_list),
    (0x18, 0x02): ("audio_record_cmd_reply", _audio_record_cmd),
    (0x18, 0x03): ("ai_chat_start_cmd_reply", _single_bool),
    (0x18, 0x85): ("ai_chat_language_reply", _single_value),
    (0x19, 0x81): ("media_control_reply", _inverted_enable),
    (0x19, 0x82): ("volume_control_reply", _inverted_enable),
    (0x1B, 0x02): ("vibration_switch_reply", _single_bool),
    (0x1B, 0x04): ("emergency_sound_reply", _emergency_sound),
    (0x20, 0x84): ("wear_check_reply", _wear_check),
    (0x20, 0x03): ("hear_protect_cur_db_reply", _single_value),
    (0x20, 0x04): ("hearing_health_realtime_reply", _hearing_health_realtime),
    (0x20, 0x05): ("hearing_health_avg_reply", _hearing_health_avg),
    (0x2A, 0x01): ("wifi_info_changed", _wifi_info_changed),
    (0x41, 0x88): ("fun_switch_reply", _fun_switch),
    (0x41, 0x87): ("prompt_tone_switch_reply", _fun_switch),
    (0x41, 0x07): ("prompt_tone_switch_value", _single_value),
    (0x41, 0x08): ("fun_switch_value", _single_value),
    (0xFA, 0x02): ("delete_wallpaper", _emergency_reply_stub),
    (0xFA, 0x03): ("restore_factory", _emergency_reply_stub),
    (0xFF, 0x02): ("ir_sensor_data", _ir_sensor),
    (0xFF, 0x01): ("beta_data_collection_reply", _hex_blob),
    (0xFF, 0x03): ("beta_double_click_status_reply", _single_value),
    (0xFF, 0x07): (
        "tdk_mic_debug_reply",
        lambda p: {"mic_a": _bool(p, 0), "mic_b": _bool(p, 1), "mic_c": _bool(p, 2)},
    ),
    (0xFF, 0x8B): ("key_down_report_str", lambda p: {"ascii": p.decode("ascii", "replace")}),
}

# groups 0x2A/0x01..0x06 all carry the same wifi push
for _c in range(0x02, 0x07):
    _PARSERS[(0x2A, _c)] = ("wifi_info_changed", _wifi_info_changed)


def parse_event(frame: Frame) -> ParsedEvent:
    key = (frame.group, frame.command)
    entry = _PARSERS.get(key)
    if entry is not None:
        name, parser = entry
        fields: dict[str, Any]
        try:
            fields = dict(parser(frame.payload))
        except Exception as exc:  # a short/truncated frame -- surface it, don't crash
            fields = {"raw": frame.payload.hex(), "parse_error": repr(exc)}
        return ParsedEvent(name, frame.group, frame.command, fields, frame)

    # no dedicated parser. A short-payload reply to a set_* (high bit) opcode is a
    # bare acknowledgement (EVENTS.md); anything else is just unrecognised.
    bare = bool(frame.command & 0x80) and len(frame.payload) <= 2
    tag = f"{frame.group:02x}_{frame.command:02x}"
    name = f"ack_{tag}" if bare else f"event_{tag}"
    return ParsedEvent(
        name,
        frame.group,
        frame.command,
        {"raw": frame.payload.hex()},
        frame,
        bare_ack=bare,
    )


EVENT_NAMES = sorted({name for name, _ in _PARSERS.values()})
