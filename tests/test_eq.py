import pytest

from soundcore.protocol import (
    GraphicEqCurve,
    ParametricEqCurve,
    ParametricPoint,
    graphic_gain_byte,
    parametric_gain_byte,
    parametric_q_byte,
    posture_ctx,
    read_gain_db,
    round_half_up,
)


def test_round_half_up_matches_java_math_round():
    assert round_half_up(0.5) == 1
    assert round_half_up(-0.5) == 0  # floor(x + 0.5): -0.5 -> floor(0.0) = 0
    assert round_half_up(2.5) == 3
    assert round_half_up(-2.5) == -2


def test_graphic_gain_byte_reference_values():
    assert graphic_gain_byte(4.0) == 0x28
    assert graphic_gain_byte(-4.0) == 0xD8
    assert graphic_gain_byte(0.0) == 0x00
    assert graphic_gain_byte(6.0) == 60
    assert graphic_gain_byte(-6.0) == (-60 & 0xFF)


def test_read_gain_db_is_biased_unsigned():
    assert read_gain_db(120) == 0.0
    assert read_gain_db(60) == -6.0
    assert read_gain_db(180) == 6.0
    assert read_gain_db(0) == -6.0     # clamped up to 60
    assert read_gain_db(255) == 6.0    # clamped down to 180


def test_send_and_read_encodings_do_not_round_trip():
    # a +4 dB slot is 0x28 on the wire when SET, but the device REPORTS +4 dB as 160
    assert graphic_gain_byte(4.0) == 0x28
    assert read_gain_db(0x28) != 4.0            # echoing snapshot bytes would corrupt
    assert read_gain_db(160) == 4.0


def test_graphic_curve_lr10_layout():
    curve = GraphicEqCurve(left=[4.0, -4.0, 0, 0, 0, 0, 0, 0])
    wire = curve.encode("lr10")
    assert len(wire) == 20
    assert wire[0] == 0x28 and wire[1] == 0xD8
    assert wire[10] == 0x28 and wire[11] == 0xD8  # right defaults to a copy of left


def test_graphic_curve_layout_lengths():
    curve = GraphicEqCurve(left=[1.0] * 8)
    assert len(curve.encode("one_channel")) == 10
    assert len(curve.encode("lr8")) == 16
    assert len(curve.encode("lr10")) == 20
    assert len(curve.encode("lr10_wide")) == 40
    assert len(curve.encode("lr10_real")) == 40


def test_graphic_curve_from_inbound():
    curve = GraphicEqCurve.from_inbound(bytes([160, 80] + [120] * 8))
    assert curve.left[0] == 4.0
    assert curve.left[1] == -4.0
    assert curve.left[2] == 0.0


def test_parametric_scalar_encoders():
    assert parametric_gain_byte(0.0) == 120     # +12 bias * 10
    assert parametric_gain_byte(-12.0) == 0
    assert parametric_q_byte(1.0) == 10
    assert parametric_q_byte(2.5) == 25


def test_parametric_fixed10_is_31_bytes():
    curve = ParametricEqCurve(points=[ParametricPoint(10, 3.0, 1.4)], ctx=0)
    wire = curve.encode("fixed10")
    assert len(wire) == 31
    assert wire[0] == 0  # ctx
    assert wire[1] == parametric_gain_byte(3.0)
    assert wire[2] == 10
    assert wire[3] == parametric_q_byte(1.4)


def test_parametric_delta_mask_is_be16():
    pts = [ParametricPoint(1, 1.0), ParametricPoint(2, 2.0), None, ParametricPoint(4, 4.0)]
    wire = ParametricEqCurve(points=pts, ctx=0).encode("delta3b")
    mask = (wire[1] << 8) | wire[2]
    assert mask == 0b1011  # points 0,1,3 present
    assert len(wire) == 3 + 3 * 3


def test_posture_ctx_bitfield():
    assert posture_ctx() == 0
    assert posture_ctx(standing=True) == 0x01
    assert posture_ctx(laying=True) == 0x02
    assert posture_ctx(hanging=True) == 0x04
    assert posture_ctx(standing=True, hanging=True) == 0x05


def test_unknown_layout_raises():
    with pytest.raises(ValueError):
        GraphicEqCurve(left=[0]).encode("nope")
