"""Host -> device command builders (COMMANDS.md, OPCODES.md).

Every method returns a ready-to-send frame (`bytes`) built via
`protocol.build_command`, so the route byte and checksum are handled centrally.

Single-payload toggles/reads are one-liners grouped at the end of the class;
commands with real payload structure are spelled out above them. Opcodes not
covered here can still be sent with `Commands.raw(group, command, payload)`.
"""

from __future__ import annotations

from .protocol import (
    AmbientMode,
    GraphicEqCurve,
    ParametricEqCurve,
    build_command,
)


class Commands:
    """Namespace of frame builders. Stateless -- every method returns `bytes`."""

    # -- generic escape hatch ------------------------------------------------
    @staticmethod
    def raw(group: int, command: int, payload: bytes = b"", *, route: int | None = None) -> bytes:
        return build_command(group, command, payload, route=route)

    # -- zero-payload requests referenced by the library itself -------------
    @staticmethod
    def request_device_info() -> bytes:
        """0x01/0x01 -- reply is the per-model connect-time snapshot."""
        return build_command(0x01, 0x01)

    @staticmethod
    def get_battery() -> bytes:
        """0x01/0x03 -- reply: left/right/case bar level (0..9)."""
        return build_command(0x01, 0x03)

    @staticmethod
    def request_eq() -> bytes:
        """0x02/0x01 -- reply: EQ index + embedded curve (read-side encoding)."""
        return build_command(0x02, 0x01)

    @staticmethod
    def request_ambient_details() -> bytes:
        """0x06/0x01 -- reply: mode / nc / transparency / custom-nc levels."""
        return build_command(0x06, 0x01)

    # -- EQ (group 0x02) --------------------------------------------------
    @staticmethod
    def set_eq_preset(index: int, curve: GraphicEqCurve) -> bytes:
        """0x02/0x81 -- LE16 index || 20-byte L/R graphic curve (slots 0..9)."""
        payload = (index & 0xFFFF).to_bytes(2, "little") + curve.encode("lr10")
        return build_command(0x02, 0x81, payload)

    @staticmethod
    def set_eq_preset_real(index: int, curve: GraphicEqCurve) -> bytes:
        """0x02/0x83 -- LE16 index || 40-byte L/R/realL/realR graphic curve."""
        payload = (index & 0xFFFF).to_bytes(2, "little") + curve.encode("lr10_real")
        return build_command(0x02, 0x83, payload)

    @staticmethod
    def set_graphic_eq_8band(payload: bytes) -> bytes:
        """0x02/0x88 -- graphic-EQ delta blob (opaque here; build it upstream)."""
        return build_command(0x02, 0x88, payload)

    @staticmethod
    def set_parametric_eq(curve: ParametricEqCurve, *, layout: str = "delta3b") -> bytes:
        """0x02/0x8D -- parametric EQ, posture-aware."""
        return build_command(0x02, 0x8D, curve.encode(layout))

    @staticmethod
    def set_full_band_eq(curve: ParametricEqCurve, *, layout: str = "delta3b") -> bytes:
        """0x02/0x87 -- parametric EQ without the posture context on some models."""
        return build_command(0x02, 0x87, curve.encode(layout))

    # -- ambient sound (group 0x06) ------------------------------------------
    @staticmethod
    def set_ambient_mode(
        mode: AmbientMode | int,
        nc_level: int = 0,
        transparency_level: int = 0,
        custom_nc: int = 0xFF,
    ) -> bytes:
        """0x06/0x81, 4-byte form. `mode` clamps to NORMAL (2); `nc_level` 0..3;
        `transparency_level` 0..2; `custom_nc` 0..10 or 0xFF when N/A."""
        m = int(mode)
        m = m if m in (0, 1, 2) else 2
        payload = bytes(
            [
                m,
                max(0, min(3, nc_level)),
                max(0, min(2, transparency_level)),
                custom_nc & 0xFF if custom_nc == 0xFF else max(0, min(10, custom_nc)),
            ]
        )
        return build_command(0x06, 0x81, payload)

    @staticmethod
    def set_ambient_mode_extended(
        option: int,
        automation_mode: int,
        transparency_option: int,
        auto_nc: int,
        manual_nc: int,
        auto_transp: int,
        manual_transp: int,
        nc_multi_scene: int,
        transp_multi_scene: int,
    ) -> bytes:
        """0x06/0x81, 7-byte form used by some model families. The two nibble bytes
        pack ((a & 0xFF) << 4) | (b & 0x0F). Field order is [confirm]."""

        def nib(a: int, b: int) -> int:
            return ((a & 0xFF) << 4) | (b & 0x0F)

        payload = bytes(
            [
                option & 0xFF,
                automation_mode & 0xFF,
                transparency_option & 0xFF,
                nib(auto_nc, manual_nc),
                nib(auto_transp, manual_transp),
                nc_multi_scene & 0xFF,
                transp_multi_scene & 0xFF,
            ]
        )
        return build_command(0x06, 0x81, payload)

    @staticmethod
    def set_custom_btn_anc_selected(
        nc: bool = False,
        transparency: bool = False,
        normal: bool = False,
        aux1: bool = False,
        aux2: bool = False,
    ) -> bytes:
        """0x06/0x82 -- which ambient modes the touch "cycle" gesture steps through.
        bit0 nc, bit1 transp, bit2 normal, bit4 aux1, bit5 aux2 (bit3 unused)."""
        b = (
            (0x01 if nc else 0)
            | (0x02 if transparency else 0)
            | (0x04 if normal else 0)
            | (0x10 if aux1 else 0)
            | (0x20 if aux2 else 0)
        )
        return build_command(0x06, 0x82, bytes([b]))

    @staticmethod
    def set_wind_suppression(enable: bool) -> bytes:
        """0x06/0x87 -- the builder writes the *inverted* boolean. Wire `0` may mean
        enabled [confirm polarity]."""
        return build_command(0x06, 0x87, bytes([0 if enable else 1]))

    # -- charging case (group 0x07) --------------------------------------
    @staticmethod
    def set_charging_box_display(
        remote_camera: bool, locate_device: bool, spatial_audio: bool, barometer: bool
    ) -> bytes:
        """0x07/0x87 -- four booleans."""
        payload = bytes(
            [
                1 if remote_camera else 0,
                1 if locate_device else 0,
                1 if spatial_audio else 0,
                1 if barometer else 0,
            ]
        )
        return build_command(0x07, 0x87, payload)

    # -- touch remap (group 0x04) -----------------------------------------
    @staticmethod
    def set_touch_action(key: int, action_a: int, action_b: int, *, enable: bool = True) -> bytes:
        """0x04/0x81 -- [enable, key, (action_a << 4) | (action_b & 0x0F)].
        Builders emit `!enable`, so wire `0` == enabled [confirm]."""
        packed = ((action_a & 0xFF) << 4) | (action_b & 0x0F)
        return build_command(0x04, 0x81, bytes([0 if enable else 1, key & 0xFF, packed]))

    @staticmethod
    def set_touch_gesture(slot: int, value: int) -> bytes:
        """0x01/0x92 -- 6-byte slot array, all 0xFF except payload[slot] = value."""
        buf = bytearray([0xFF] * 6)
        buf[slot] = value & 0xFF
        return build_command(0x01, 0x92, bytes(buf))

    # -- power / time (group 0x01) --------------------------------------
    @staticmethod
    def sync_time(epoch_seconds: int, *, big_endian: bool = False, tz_byte: int | None = None) -> bytes:
        """0x01/0xA6 -- epoch seconds as a 32-bit int. One vendor builder emits BE32,
        another LE32 (open item #4); default LE32. Optional trailing tz byte."""
        order = "big" if big_endian else "little"
        payload = (epoch_seconds & 0xFFFFFFFF).to_bytes(4, order)
        if tz_byte is not None:
            payload += bytes([tz_byte & 0xFF])
        return build_command(0x01, 0xA6, payload)

    @staticmethod
    def set_alarm_list(epoch_times: list[int]) -> bytes:
        """0x01/0xA7 -- N little-endian uint32 alarm times."""
        payload = b"".join((t & 0xFFFFFFFF).to_bytes(4, "little") for t in epoch_times)
        return build_command(0x01, 0xA7, payload)

    @staticmethod
    def set_play_countdown_time(minutes: int) -> bytes:
        """0x01/0xB3 -- [hi, lo] big-endian uint16 minutes."""
        return build_command(0x01, 0xB3, bytes([(minutes >> 8) & 0xFF, minutes & 0xFF]))

    # -- HearID / personal NC (group 0x03) -----------------------------------
    @staticmethod
    def start_or_cancel_personal_nc(start: bool, arg: int = 0, tail: int = 0) -> bytes:
        """0x03/0x88 -- [start bool, BE32 arg, u8 tail]."""
        payload = bytes([1 if start else 0]) + (arg & 0xFFFFFFFF).to_bytes(4, "big") + bytes([tail & 0xFF])
        return build_command(0x03, 0x88, payload)

    @staticmethod
    def set_hearid_audio(on: bool, a: int = 0, b: int = 0, c: int = 0, d: int = 0) -> bytes:
        """0x03/0x92 -- [on bool, a, b, c, d]."""
        return build_command(0x03, 0x92, bytes([1 if on else 0, a & 0xFF, b & 0xFF, c & 0xFF, d & 0xFF]))

    # -- gaming (group 0x0D) -----------------------------------------------
    @staticmethod
    def set_gaming_mode(
        anticlockwise: bool,
        state: int,
        seconds: int,
        milliseconds: int,
        colour_state: int,
        final_colour: int,
    ) -> bytes:
        """0x0D/0x81 -- 9 bytes: [dir u8, state u8, LE16 sec, LE16 ms, LE16 colour_state, u8 final]."""
        payload = (
            bytes([1 if anticlockwise else 0, state & 0xFF])
            + (seconds & 0xFFFF).to_bytes(2, "little")
            + (milliseconds & 0xFFFF).to_bytes(2, "little")
            + (colour_state & 0xFFFF).to_bytes(2, "little")
            + bytes([final_colour & 0xFF])
        )
        return build_command(0x0D, 0x81, payload)

    # -- lighting (group 0x0E) ------------------------------------------
    @staticmethod
    def set_light_effect(enable: int, mode: int, colour_index: int) -> bytes:
        """0x0E/0x83 -- [enable u8, mode u8, colour_index u8]."""
        return build_command(0x0E, 0x83, bytes([enable & 0xFF, mode & 0xFF, colour_index & 0xFF]))

    # -- spatial / find (group 0x10) --------------------------------------
    @staticmethod
    def set_spatial_audio_status(switch: bool, effect_mode: int, sound_mode: int) -> bytes:
        """0x10/0x81 -- [switch bool, effect_mode u8, sound_mode u8]."""
        return build_command(
            0x10, 0x81, bytes([1 if switch else 0, effect_mode & 0xFF, sound_mode & 0xFF])
        )

    @staticmethod
    def set_find_device(left: bool, right: bool, case: bool) -> bytes:
        """0x10/0x87 -- start/stop the locate tone per component."""
        return build_command(
            0x10, 0x87, bytes([1 if left else 0, 1 if right else 0, 1 if case else 0])
        )

    # -- sleep sound / alarms (groups 0x13, 0x14) ------------------------
    @staticmethod
    def set_sound_id_to_play(index: int, play: bool) -> bytes:
        """0x13/0x02 -- [index u8, play bool]."""
        return build_command(0x13, 0x02, bytes([index & 0xFF, 1 if play else 0]))

    @staticmethod
    def set_alarm(
        alarm_id: int,
        enabled: bool,
        minute_of_day: int,
        repeat_mask: int,
        sound_id: int,
        volume: int,
        snooze_minutes: int | None = None,
    ) -> bytes:
        """0x14/0x81 -- 7 bytes, or 8 when `snooze_minutes` is given.
        `minute_of_day` is written low byte then high byte."""
        payload = bytearray(
            [
                alarm_id & 0xFF,
                1 if enabled else 0,
                minute_of_day & 0xFF,
                (minute_of_day >> 8) & 0xFF,
                repeat_mask & 0xFF,
                sound_id & 0xFF,
                volume & 0xFF,
            ]
        )
        if snooze_minutes is not None:
            payload.append(snooze_minutes & 0xFF)
        return build_command(0x14, 0x81, bytes(payload))

    @staticmethod
    def set_one_use_alarm(enabled: bool, minute_of_day: int, sound_id: int, volume: int) -> bytes:
        """0x14/0x84 -- [enabled u8, LE16 minute_of_day, sound_id u8, volume u8]."""
        payload = bytes(
            [
                1 if enabled else 0,
                minute_of_day & 0xFF,
                (minute_of_day >> 8) & 0xFF,
                sound_id & 0xFF,
                volume & 0xFF,
            ]
        )
        return build_command(0x14, 0x84, payload)

    # -- karaoke / emergency (groups 0x17, 0x1B) -------------------------
    @staticmethod
    def set_stage_reverb(index: int, intensity: int) -> bytes:
        """0x17/0x01 -- [index u8, intensity u8]."""
        return build_command(0x17, 0x01, bytes([index & 0xFF, intensity & 0xFF]))

    @staticmethod
    def set_emergency_sound(sound_id: int, play_time: int, play_status: int) -> bytes:
        """0x1B/0x03 -- [sound_id u8, play_time u8, play_status u8]."""
        return build_command(0x1B, 0x03, bytes([sound_id & 0xFF, play_time & 0xFF, play_status & 0xFF]))

    # -- multi-device MAC ops (group 0x0B) ------------------------------
    @staticmethod
    def _mac_bytes(mac: str) -> bytes:
        raw = bytes(int(p, 16) for p in mac.replace("-", ":").split(":"))
        if len(raw) != 6:
            raise ValueError(f"expected a 6-octet MAC, got {mac!r}")
        return raw

    @classmethod
    def connect_mac_device(cls, mac: str) -> bytes:
        return build_command(0x0B, 0x82, cls._mac_bytes(mac))

    @classmethod
    def disconnect_mac_device(cls, mac: str) -> bytes:
        return build_command(0x0B, 0x81, cls._mac_bytes(mac))

    @classmethod
    def delete_mac_from_history(cls, mac: str) -> bytes:
        return build_command(0x0B, 0x83, cls._mac_bytes(mac))

    # -- fun-switch bank (group 0x41) ----------------------------------
    @staticmethod
    def set_fun_switch(bit: int, value: int) -> bytes:
        """0x41/0x88 -- [bit u8, value u8]. Bit table: protocol.FUN_SWITCH_BITS_*."""
        return build_command(0x41, 0x88, bytes([bit & 0xFF, value & 0xFF]))

    # -- Wi-Fi provisioning (group 0x1A) ---------------------------------
    @staticmethod
    def send_wifi_info_plaintext(ssid: str, password: str, area: str = "") -> bytes:
        """0x1A/0x05 -- plaintext fallback form:
        [ssid_len u8, ssid, pwd_len u8, pwd, area_len u8, area]. The encrypted
        form (AES-CTR keyed on the reversed device MAC) is not implemented here."""
        s = ssid.encode()
        p = password.encode()
        a = area.encode()
        payload = bytes([len(s)]) + s + bytes([len(p)]) + p + bytes([len(a)]) + a
        return build_command(0x1A, 0x05, payload)

    # ==== single-payload builders (one line each; see COMMANDS.md) ====

    @staticmethod
    def get_tws_state() -> bytes:
        """0x01/0x02."""
        return build_command(0x01, 0x02)

    @staticmethod
    def get_charging() -> bytes:
        """0x01/0x04."""
        return build_command(0x01, 0x04)

    @staticmethod
    def request_device_info_alt() -> bytes:
        """0x01/0x05."""
        return build_command(0x01, 0x05)

    @staticmethod
    def get_ear_form() -> bytes:
        """0x01/0x10."""
        return build_command(0x01, 0x10)

    @staticmethod
    def get_game_switch() -> bytes:
        """0x01/0x11."""
        return build_command(0x01, 0x11)

    @staticmethod
    def get_super_hearing() -> bytes:
        """0x01/0x12."""
        return build_command(0x01, 0x12)

    @staticmethod
    def get_cur_mode() -> bytes:
        """0x01/0x14."""
        return build_command(0x01, 0x14)

    @staticmethod
    def get_play_pause() -> bytes:
        """0x01/0x15."""
        return build_command(0x01, 0x15)

    @staticmethod
    def set_wear_detection(flag: bool) -> bytes:
        """0x01/0x81."""
        return build_command(0x01, 0x81, bytes([1 if flag else 0]))

    @staticmethod
    def set_touch_tone(flag: bool) -> bytes:
        """0x01/0x83."""
        return build_command(0x01, 0x83, bytes([1 if flag else 0]))

    @staticmethod
    def set_side_tone(flag: bool) -> bytes:
        """0x01/0x84."""
        return build_command(0x01, 0x84, bytes([1 if flag else 0]))

    @staticmethod
    def set_auto_power_off(flag: bool, value: int) -> bytes:
        """0x01/0x86."""
        return build_command(0x01, 0x86, bytes([1 if flag else 0, value & 0xFF]))

    @staticmethod
    def set_game_mode(flag: bool) -> bytes:
        """0x01/0x87."""
        return build_command(0x01, 0x87, bytes([1 if flag else 0]))

    @staticmethod
    def set_volume(value: int) -> bytes:
        """0x01/0x88."""
        return build_command(0x01, 0x88, bytes([value & 0xFF]))

    @staticmethod
    def set_long_press_power_off(flag: bool) -> bytes:
        """0x01/0x89."""
        return build_command(0x01, 0x89, bytes([1 if flag else 0]))

    @staticmethod
    def set_sound_source(value: int) -> bytes:
        """0x01/0x8B."""
        return build_command(0x01, 0x8B, bytes([value & 0xFF]))

    @staticmethod
    def set_in_ear_tone(flag: bool) -> bytes:
        """0x01/0x8C."""
        return build_command(0x01, 0x8C, bytes([1 if flag else 0]))

    @staticmethod
    def set_prompt_language(value: int) -> bytes:
        """0x01/0x8D."""
        return build_command(0x01, 0x8D, bytes([value & 0xFF]))

    @staticmethod
    def set_ambient_notice_switch(flag: bool) -> bytes:
        """0x01/0x8E."""
        return build_command(0x01, 0x8E, bytes([1 if flag else 0]))

    @staticmethod
    def set_power_off(flag: bool) -> bytes:
        """0x01/0x8F."""
        return build_command(0x01, 0x8F, bytes([1 if flag else 0]))

    @staticmethod
    def disconnect_device() -> bytes:
        """0x01/0x93."""
        return build_command(0x01, 0x93)

    @staticmethod
    def set_power_on_battery_notice(flag: bool) -> bytes:
        """0x01/0x94."""
        return build_command(0x01, 0x94, bytes([1 if flag else 0]))

    @staticmethod
    def set_super_hearing(flag: bool) -> bytes:
        """0x01/0xA1."""
        return build_command(0x01, 0xA1, bytes([1 if flag else 0]))

    @staticmethod
    def set_call_mix(flag: bool) -> bytes:
        """0x01/0xA2."""
        return build_command(0x01, 0xA2, bytes([1 if flag else 0]))

    @staticmethod
    def set_microphone(flag: bool) -> bytes:
        """0x01/0xA3."""
        return build_command(0x01, 0xA3, bytes([1 if flag else 0]))

    @staticmethod
    def set_cur_mode(value: int) -> bytes:
        """0x01/0xA9."""
        return build_command(0x01, 0xA9, bytes([value & 0xFF]))

    @staticmethod
    def set_smart_play_switch(flag: bool) -> bytes:
        """0x01/0xAA."""
        return build_command(0x01, 0xAA, bytes([1 if flag else 0]))

    @staticmethod
    def set_custom_play_time(value: int) -> bytes:
        """0x01/0xAB."""
        return build_command(0x01, 0xAB, bytes([value & 0xFF]))

    @staticmethod
    def set_adaptive_noise(flag: bool) -> bytes:
        """0x01/0xAC."""
        return build_command(0x01, 0xAC, bytes([1 if flag else 0]))

    @staticmethod
    def set_abnormal_sound_remind(flag: bool) -> bytes:
        """0x01/0xAD."""
        return build_command(0x01, 0xAD, bytes([1 if flag else 0]))

    @staticmethod
    def reset_sleep_time() -> bytes:
        """0x01/0xB0."""
        return build_command(0x01, 0xB0)

    @staticmethod
    def set_play_pause(flag: bool) -> bytes:
        """0x01/0xB2."""
        return build_command(0x01, 0xB2, bytes([1 if flag else 0]))

    @staticmethod
    def get_device_storage() -> bytes:
        """0x01/0xB6."""
        return build_command(0x01, 0xB6)

    @staticmethod
    def get_device_indicator_status() -> bytes:
        """0x01/0xB7."""
        return build_command(0x01, 0xB7)

    @staticmethod
    def get_query_device_status() -> bytes:
        """0x01/0xBC."""
        return build_command(0x01, 0xBC)

    @staticmethod
    def set_sound_quality(flag: bool) -> bytes:
        """0x01/0xFF."""
        return build_command(0x01, 0xFF, bytes([1 if flag else 0]))

    @staticmethod
    def get_3d_effect() -> bytes:
        """0x02/0x06."""
        return build_command(0x02, 0x06)

    @staticmethod
    def set_bass_up(flag: bool) -> bytes:
        """0x02/0x84."""
        return build_command(0x02, 0x84, bytes([1 if flag else 0]))

    @staticmethod
    def set_stereo_expansion(flag: bool, value: int) -> bytes:
        """0x02/0x85."""
        return build_command(0x02, 0x85, bytes([1 if flag else 0, value & 0xFF]))

    @staticmethod
    def set_3d_effect(flag: bool) -> bytes:
        """0x02/0x86."""
        return build_command(0x02, 0x86, bytes([1 if flag else 0]))

    @staticmethod
    def get_adaptive_eq_detail() -> bytes:
        """0x02/0x89."""
        return build_command(0x02, 0x89)

    @staticmethod
    def switch_adaptive_eq(flag: bool) -> bytes:
        """0x02/0x8A."""
        return build_command(0x02, 0x8A, bytes([1 if flag else 0]))

    @staticmethod
    def set_speaker_eq_index(value: int) -> bytes:
        """0x02/0x8B."""
        return build_command(0x02, 0x8B, bytes([value & 0xFF]))

    @staticmethod
    def get_adaptive_eq_direction() -> bytes:
        """0x02/0x8C."""
        return build_command(0x02, 0x8C)

    @staticmethod
    def get_valid_eq_index() -> bytes:
        """0x02/0x8E."""
        return build_command(0x02, 0x8E)

    @staticmethod
    def get_eq_index_report() -> bytes:
        """0x02/0x8F."""
        return build_command(0x02, 0x8F)

    @staticmethod
    def set_hearid_switch(flag: bool) -> bytes:
        """0x03/0x81."""
        return build_command(0x03, 0x81, bytes([1 if flag else 0]))

    @staticmethod
    def start_or_cancel_hearid_test(value: int) -> bytes:
        """0x03/0x83."""
        return build_command(0x03, 0x83, bytes([value & 0xFF]))

    @staticmethod
    def reset_hearid_data() -> bytes:
        """0x03/0x84."""
        return build_command(0x03, 0x84)

    @staticmethod
    def reset_personal_nc() -> bytes:
        """0x03/0x89."""
        return build_command(0x03, 0x89)

    @staticmethod
    def set_personal_nc_switch(flag: bool) -> bytes:
        """0x03/0x90."""
        return build_command(0x03, 0x90, bytes([1 if flag else 0]))

    @staticmethod
    def get_personal_nc_switch() -> bytes:
        """0x03/0x91."""
        return build_command(0x03, 0x91)

    @staticmethod
    def get_hearid_test_result() -> bytes:
        """0x03/0x94."""
        return build_command(0x03, 0x94)

    @staticmethod
    def set_voice_settings(flag: bool, value: int) -> bytes:
        """0x04/0x10."""
        return build_command(0x04, 0x10, bytes([1 if flag else 0, value & 0xFF]))

    @staticmethod
    def reset_custom_btn(value: int) -> bytes:
        """0x04/0x82."""
        return build_command(0x04, 0x82, bytes([value & 0xFF]))

    @staticmethod
    def set_press_sensitivity(value: int) -> bytes:
        """0x04/0x85."""
        return build_command(0x04, 0x85, bytes([value & 0xFF]))

    @staticmethod
    def enable_wear_btn_relate(flag: bool) -> bytes:
        """0x04/0x86."""
        return build_command(0x04, 0x86, bytes([1 if flag else 0]))

    @staticmethod
    def delete_user_data(value: int) -> bytes:
        """0x05/0x81."""
        return build_command(0x05, 0x81, bytes([value & 0xFF]))

    @staticmethod
    def get_custom_btn_anc_selected() -> bytes:
        """0x06/0x02."""
        return build_command(0x06, 0x02)

    @staticmethod
    def get_ambient_switch() -> bytes:
        """0x06/0x07."""
        return build_command(0x06, 0x07)

    @staticmethod
    def get_smart_nc_switch() -> bytes:
        """0x06/0x08."""
        return build_command(0x06, 0x08)

    @staticmethod
    def set_ambient_switch(flag: bool) -> bytes:
        """0x06/0x83."""
        return build_command(0x06, 0x83, bytes([1 if flag else 0]))

    @staticmethod
    def set_environment_detection_prompt(flag: bool) -> bytes:
        """0x06/0x85."""
        return build_command(0x06, 0x85, bytes([1 if flag else 0]))

    @staticmethod
    def set_smart_nc_switch(flag: bool) -> bytes:
        """0x06/0x88."""
        return build_command(0x06, 0x88, bytes([1 if flag else 0]))

    @staticmethod
    def get_ears_in_case() -> bytes:
        """0x07/0x02."""
        return build_command(0x07, 0x02)

    @staticmethod
    def get_charging_box_connected() -> bytes:
        """0x07/0x04."""
        return build_command(0x07, 0x04)

    @staticmethod
    def get_ota_enable() -> bytes:
        """0x07/0x05."""
        return build_command(0x07, 0x05)

    @staticmethod
    def get_charging_box_display() -> bytes:
        """0x07/0x07."""
        return build_command(0x07, 0x07)

    @staticmethod
    def prepare_charging_box_ota() -> bytes:
        """0x07/0x89."""
        return build_command(0x07, 0x89)

    @staticmethod
    def set_charging_box_language(value: int) -> bytes:
        """0x07/0x8A."""
        return build_command(0x07, 0x8A, bytes([value & 0xFF]))

    @staticmethod
    def get_wear_fit_detection() -> bytes:
        """0x09/0x01."""
        return build_command(0x09, 0x01)

    @staticmethod
    def get_wear_status() -> bytes:
        """0x09/0x02."""
        return build_command(0x09, 0x02)

    @staticmethod
    def set_voice_control(flag: bool, value: int) -> bytes:
        """0x0A/0x81."""
        return build_command(0x0A, 0x81, bytes([1 if flag else 0, value & 0xFF]))

    @staticmethod
    def set_super_volume(flag: bool, value: int) -> bytes:
        """0x0A/0x82."""
        return build_command(0x0A, 0x82, bytes([1 if flag else 0, value & 0xFF]))

    @staticmethod
    def request_connect_history() -> bytes:
        """0x0B/0x01."""
        return build_command(0x0B, 0x01)

    @staticmethod
    def get_dual_device_audio_focus() -> bytes:
        """0x0B/0x02."""
        return build_command(0x0B, 0x02)

    @staticmethod
    def set_connect_device_max(value: int) -> bytes:
        """0x0B/0x05."""
        return build_command(0x0B, 0x05, bytes([value & 0xFF]))

    @staticmethod
    def set_gaming_state(flag: bool) -> bytes:
        """0x0D/0x82."""
        return build_command(0x0D, 0x82, bytes([1 if flag else 0]))

    @staticmethod
    def request_all_light_effects() -> bytes:
        """0x0E/0x01."""
        return build_command(0x0E, 0x01)

    @staticmethod
    def get_brightness_value() -> bytes:
        """0x0E/0x06."""
        return build_command(0x0E, 0x06)

    @staticmethod
    def set_brightness_switch(flag: bool) -> bytes:
        """0x0E/0x08."""
        return build_command(0x0E, 0x08, bytes([1 if flag else 0]))

    @staticmethod
    def get_brightness_switch() -> bytes:
        """0x0E/0x09."""
        return build_command(0x0E, 0x09)

    @staticmethod
    def set_light_effect_brightness(value: int) -> bytes:
        """0x0E/0x82."""
        return build_command(0x0E, 0x82, bytes([value & 0xFF]))

    @staticmethod
    def set_light_effect_mode(value: int) -> bytes:
        """0x0E/0x86."""
        return build_command(0x0E, 0x86, bytes([value & 0xFF]))

    @staticmethod
    def set_light_effect_switch(flag: bool) -> bytes:
        """0x0E/0x87."""
        return build_command(0x0E, 0x87, bytes([1 if flag else 0]))

    @staticmethod
    def get_spatial_audio_status() -> bytes:
        """0x10/0x01."""
        return build_command(0x10, 0x01)

    @staticmethod
    def get_find_device_state() -> bytes:
        """0x10/0x09."""
        return build_command(0x10, 0x09)

    @staticmethod
    def set_nap(flag: bool, value: int) -> bytes:
        """0x10/0x61."""
        return build_command(0x10, 0x61, bytes([1 if flag else 0, value & 0xFF]))

    @staticmethod
    def set_env_sound_detect(flag: bool) -> bytes:
        """0x10/0x69."""
        return build_command(0x10, 0x69, bytes([1 if flag else 0]))

    @staticmethod
    def get_auracast_switch() -> bytes:
        """0x10/0x70."""
        return build_command(0x10, 0x70)

    @staticmethod
    def set_auracast_switch(flag: bool) -> bytes:
        """0x10/0x71."""
        return build_command(0x10, 0x71, bytes([1 if flag else 0]))

    @staticmethod
    def set_sleep_scene_switch(flag: bool) -> bytes:
        """0x10/0x72."""
        return build_command(0x10, 0x72, bytes([1 if flag else 0]))

    @staticmethod
    def set_call_alert_switch(flag: bool) -> bytes:
        """0x10/0x75."""
        return build_command(0x10, 0x75, bytes([1 if flag else 0]))

    @staticmethod
    def set_music_rush(flag: bool) -> bytes:
        """0x10/0x76."""
        return build_command(0x10, 0x76, bytes([1 if flag else 0]))

    @staticmethod
    def set_anc_tone_switch(flag: bool) -> bytes:
        """0x10/0x77."""
        return build_command(0x10, 0x77, bytes([1 if flag else 0]))

    @staticmethod
    def set_low_battery_alert_switch(flag: bool) -> bytes:
        """0x10/0x78."""
        return build_command(0x10, 0x78, bytes([1 if flag else 0]))

    @staticmethod
    def get_env_sound_detect() -> bytes:
        """0x10/0x7A."""
        return build_command(0x10, 0x7A)

    @staticmethod
    def set_nap_mode(flag: bool) -> bytes:
        """0x10/0x7B."""
        return build_command(0x10, 0x7B, bytes([1 if flag else 0]))

    @staticmethod
    def set_ambient_sound_prompt_switch(flag: bool) -> bytes:
        """0x10/0x82."""
        return build_command(0x10, 0x82, bytes([1 if flag else 0]))

    @staticmethod
    def set_media_mode_switch(flag: bool) -> bytes:
        """0x10/0x83."""
        return build_command(0x10, 0x83, bytes([1 if flag else 0]))

    @staticmethod
    def set_three_d_effect_mode(flag: bool) -> bytes:
        """0x10/0x85."""
        return build_command(0x10, 0x85, bytes([1 if flag else 0]))

    @staticmethod
    def set_leaky_switch(flag: bool) -> bytes:
        """0x10/0x86."""
        return build_command(0x10, 0x86, bytes([1 if flag else 0]))

    @staticmethod
    def set_volume_balance(value: int) -> bytes:
        """0x10/0x8C."""
        return build_command(0x10, 0x8C, bytes([value & 0xFF]))

    @staticmethod
    def set_stamina_switch(flag: bool) -> bytes:
        """0x10/0x90."""
        return build_command(0x10, 0x90, bytes([1 if flag else 0]))

    @staticmethod
    def get_stamina_switch() -> bytes:
        """0x10/0x91."""
        return build_command(0x10, 0x91)

    @staticmethod
    def set_button_brightness(value: int) -> bytes:
        """0x10/0x92."""
        return build_command(0x10, 0x92, bytes([value & 0xFF]))

    @staticmethod
    def get_button_brightness() -> bytes:
        """0x10/0x93."""
        return build_command(0x10, 0x93)

    @staticmethod
    def set_smart_talk(flag: bool) -> bytes:
        """0x10/0x94."""
        return build_command(0x10, 0x94, bytes([1 if flag else 0]))

    @staticmethod
    def switch_default_sleep_mode(flag: bool) -> bytes:
        """0x10/0x95."""
        return build_command(0x10, 0x95, bytes([1 if flag else 0]))

    @staticmethod
    def set_ambient_sound_follow(flag: bool) -> bytes:
        """0x10/0x96."""
        return build_command(0x10, 0x96, bytes([1 if flag else 0]))

    @staticmethod
    def set_touch_control_switch(flag: bool) -> bytes:
        """0x10/0x98."""
        return build_command(0x10, 0x98, bytes([1 if flag else 0]))

    @staticmethod
    def set_touch_lock(flag: bool) -> bytes:
        """0x10/0x99."""
        return build_command(0x10, 0x99, bytes([1 if flag else 0]))

    @staticmethod
    def set_eq_compensate_switch(flag: bool) -> bytes:
        """0x10/0x9A."""
        return build_command(0x10, 0x9A, bytes([1 if flag else 0]))

    @staticmethod
    def set_posture_calibration(value: int) -> bytes:
        """0x10/0x9C."""
        return build_command(0x10, 0x9C, bytes([value & 0xFF]))

    @staticmethod
    def set_device_switch_shutdown(flag: bool) -> bytes:
        """0x10/0x9E."""
        return build_command(0x10, 0x9E, bytes([1 if flag else 0]))

    @staticmethod
    def set_mode_change_tone(flag: bool) -> bytes:
        """0x10/0x9F."""
        return build_command(0x10, 0x9F, bytes([1 if flag else 0]))

    @staticmethod
    def get_immersive_status() -> bytes:
        """0x12/0x01."""
        return build_command(0x12, 0x01)

    @staticmethod
    def set_immersive_status(value: int) -> bytes:
        """0x12/0x81."""
        return build_command(0x12, 0x81, bytes([value & 0xFF]))

    @staticmethod
    def request_sound_list() -> bytes:
        """0x13/0x01."""
        return build_command(0x13, 0x01)

    @staticmethod
    def get_current_sound() -> bytes:
        """0x13/0x03."""
        return build_command(0x13, 0x03)

    @staticmethod
    def set_sound_device_volume(value: int) -> bytes:
        """0x13/0x05."""
        return build_command(0x13, 0x05, bytes([value & 0xFF]))

    @staticmethod
    def set_smart_snore_mode(flag: bool) -> bytes:
        """0x13/0x06."""
        return build_command(0x13, 0x06, bytes([1 if flag else 0]))

    @staticmethod
    def request_alarm_list() -> bytes:
        """0x14/0x01."""
        return build_command(0x14, 0x01)

    @staticmethod
    def get_next_alarm() -> bytes:
        """0x14/0x02."""
        return build_command(0x14, 0x02)

    @staticmethod
    def delete_alarm(value: int) -> bytes:
        """0x14/0x82."""
        return build_command(0x14, 0x82, bytes([value & 0xFF]))

    @staticmethod
    def get_shut_off_data() -> bytes:
        """0x15/0x03."""
        return build_command(0x15, 0x03)

    @staticmethod
    def set_sleep_data_switch(flag: bool) -> bytes:
        """0x15/0x84."""
        return build_command(0x15, 0x84, bytes([1 if flag else 0]))

    @staticmethod
    def set_smart_switch_sound_index(value: int) -> bytes:
        """0x15/0x87."""
        return build_command(0x15, 0x87, bytes([value & 0xFF]))

    @staticmethod
    def get_stage_reverb() -> bytes:
        """0x17/0x02."""
        return build_command(0x17, 0x02)

    @staticmethod
    def set_voice_modification(value: int) -> bytes:
        """0x17/0x03."""
        return build_command(0x17, 0x03, bytes([value & 0xFF]))

    @staticmethod
    def set_accompaniment_mode(value: int) -> bytes:
        """0x17/0x05."""
        return build_command(0x17, 0x05, bytes([value & 0xFF]))

    @staticmethod
    def set_accompaniment_volume(value: int) -> bytes:
        """0x17/0x07."""
        return build_command(0x17, 0x07, bytes([value & 0xFF]))

    @staticmethod
    def get_mic_connect_status() -> bytes:
        """0x17/0x09."""
        return build_command(0x17, 0x09)

    @staticmethod
    def set_vibration_switch(flag: bool) -> bytes:
        """0x1B/0x01."""
        return build_command(0x1B, 0x01, bytes([1 if flag else 0]))

    @staticmethod
    def get_vibration_switch() -> bytes:
        """0x1B/0x02."""
        return build_command(0x1B, 0x02)

    @staticmethod
    def set_loudspeaker(value: int) -> bytes:
        """0x1B/0x05."""
        return build_command(0x1B, 0x05, bytes([value & 0xFF]))

    @staticmethod
    def get_hear_protect_cur_db() -> bytes:
        """0x20/0x03."""
        return build_command(0x20, 0x03)

    @staticmethod
    def get_hearing_health_realtime() -> bytes:
        """0x20/0x04."""
        return build_command(0x20, 0x04)

    @staticmethod
    def get_hearing_health_avg() -> bytes:
        """0x20/0x05."""
        return build_command(0x20, 0x05)

    @staticmethod
    def set_hear_protect_update_frequency(value: int) -> bytes:
        """0x20/0x81."""
        return build_command(0x20, 0x81, bytes([value & 0xFF]))

    @staticmethod
    def set_hear_protect_max_value(flag: bool, value: int) -> bytes:
        """0x20/0x82."""
        return build_command(0x20, 0x82, bytes([1 if flag else 0, value & 0xFF]))

    @staticmethod
    def get_wear_check_test() -> bytes:
        """0x20/0x84."""
        return build_command(0x20, 0x84)

    @staticmethod
    def set_hear_protect(flag: bool) -> bytes:
        """0x20/0x86."""
        return build_command(0x20, 0x86, bytes([1 if flag else 0]))

    @staticmethod
    def set_hearing_health_switch(flag: bool) -> bytes:
        """0x20/0x87."""
        return build_command(0x20, 0x87, bytes([1 if flag else 0]))

    @staticmethod
    def set_hearing_health_realtime(flag: bool) -> bytes:
        """0x20/0x88."""
        return build_command(0x20, 0x88, bytes([1 if flag else 0]))

    @staticmethod
    def get_prompt_tone_switch() -> bytes:
        """0x41/0x07."""
        return build_command(0x41, 0x07)

    @staticmethod
    def get_fun_switch() -> bytes:
        """0x41/0x08."""
        return build_command(0x41, 0x08)

    @staticmethod
    def set_prompt_tone_switch(value: int) -> bytes:
        """0x41/0x87."""
        return build_command(0x41, 0x87, bytes([value & 0xFF]))

    @staticmethod
    def get_beta_data_collection() -> bytes:
        """0xFF/0x01."""
        return build_command(0xFF, 0x01)

    @staticmethod
    def set_ir_sensor_switch(flag: bool) -> bytes:
        """0xFF/0x83."""
        return build_command(0xFF, 0x83, bytes([1 if flag else 0]))


# every builder name the class exposes, for discovery / the CLI
COMMAND_NAMES = sorted(
    n
    for n in vars(Commands)
    if not n.startswith("_") and n != "raw" and callable(getattr(Commands, n))
)
