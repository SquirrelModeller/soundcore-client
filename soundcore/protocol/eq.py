"""EQ value encoding (PROTOCOL.md section 8, CORE.md section 3).

Two things a client must keep straight:

  * The host *sets* an 8-band graphic curve as a **signed** byte per slot:
        wire = s8(round_half_up(gain_db * 10))
  * The device *reports* the current custom curve (in the connect-time snapshot
    and in eq_reply / 0x02/0x01) as an **unsigned, +12-biased** byte:
        gain_db = clamp(byte, 60, 180) / 10 - 12       # -6.0 .. +6.0 dB

  These are two encodings of the same curve. Decode inbound with `read_gain_db`,
  re-encode outbound with `graphic_gain_byte`. Do not copy snapshot bytes into a
  set command.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .constants import EQ_GAIN_SCALE, EQ_SLOTS_PER_CHANNEL

# inbound biased-curve clamp bounds. Range -6..+6 dB is firm; the exact 60/180
# clamp is [confirm].
_READ_CLAMP_LO = 60
_READ_CLAMP_HI = 180
_READ_BIAS_DB = 12


def round_half_up(x: float) -> int:
    """Match the vendor encoder's rounding (Java Math.round = floor(x + 0.5))."""
    return math.floor(x + 0.5)


def _s8(value: int) -> int:
    """Low 8 bits of a signed int, as an unsigned wire byte (two's complement)."""
    return value & 0xFF


# --- 8-band graphic EQ ----------------------------------------------------

def graphic_gain_byte(gain_db: float) -> int:
    """Send-side wire byte for one graphic-EQ slot: s8(round(gain_db * 10)).

    No clamping here -- the reference app clamps band gains (typically +/-6 dB)
    beforehand. +4.0 dB -> 0x28, -4.0 dB -> 0xD8.
    """
    return _s8(round_half_up(gain_db * EQ_GAIN_SCALE))


def read_gain_db(byte: int) -> float:
    """Decode one slot of an *inbound* (snapshot / eq_reply) graphic curve."""
    clamped = max(_READ_CLAMP_LO, min(_READ_CLAMP_HI, byte & 0xFF))
    return clamped / EQ_GAIN_SCALE - _READ_BIAS_DB


def _channel_wire_ints(gains_db: list[float]) -> list[int]:
    """Ten wire ints for one channel. Slots 0..8 round; slot 9 truncates (a source
    quirk -- slot 9 is ~always 0). Missing slots are treated as 0 dB."""
    out: list[int] = []
    for k in range(EQ_SLOTS_PER_CHANNEL):
        v = gains_db[k] if k < len(gains_db) else 0.0
        scaled = v * EQ_GAIN_SCALE
        out.append(round_half_up(scaled) if k < 9 else math.trunc(scaled))
    return out


@dataclass
class GraphicEqCurve:
    """A graphic-EQ curve. `left` / `right` are gains in dB, slots 0..7 map to
    EQ_BAND_HZ; slots 8..9 are usually 0. A one-curve client leaves `right` as None
    and it is sent as a copy of `left`."""

    left: list[float]
    right: list[float] | None = None

    @classmethod
    def from_inbound(cls, curve_bytes: bytes) -> GraphicEqCurve:
        """Build from a 10- or 20-byte inbound curve (biased/unsigned encoding).
        A 20-byte blob is 10 slots + a paired copy; only the first 10 are read."""
        gains = [read_gain_db(b) for b in curve_bytes[:EQ_SLOTS_PER_CHANNEL]]
        return cls(left=gains)

    def _lr(self) -> tuple[list[int], list[int]]:
        left = _channel_wire_ints(self.left)
        right = _channel_wire_ints(self.right if self.right is not None else self.left)
        return left, right

    def encode(self, layout: str = "lr10") -> bytes:
        """Serialise to one of the graphic-EQ payload layouts (CORE.md section 3.3).

          "one_channel"  10 bytes  L g0..9
          "lr8"          16 bytes  L g0..7 || R g0..7
          "lr10"         20 bytes  L g0..9 || R g0..9         (set_eq_preset)
          "lr10_wide"    40 bytes  the 20 lr10 values, each as LE16
          "lr10_real"    40 bytes  L || R || realL || realR   (real* = plain copy
                                   when no headroom transform is applied)
        """
        left, right = self._lr()
        if layout == "one_channel":
            return bytes(_s8(v) for v in left)
        if layout == "lr8":
            return bytes(_s8(v) for v in left[:8] + right[:8])
        if layout == "lr10":
            return bytes(_s8(v) for v in left + right)
        if layout == "lr10_wide":
            out = bytearray()
            for v in left + right:
                out += (v & 0xFFFF).to_bytes(2, "little")
            return bytes(out)
        if layout == "lr10_real":
            return bytes(_s8(v) for v in left + right + left + right)
        raise ValueError(f"unknown graphic-EQ layout {layout!r}")


# --- parametric EQ ------------------------------------------------------------

_PARAM_GAIN_BIAS_DB = 12


def parametric_gain_byte(gain_db: float) -> int:
    return round_half_up((gain_db + _PARAM_GAIN_BIAS_DB) * EQ_GAIN_SCALE) & 0xFF


def parametric_q_byte(q: float) -> int:
    return round_half_up(q * EQ_GAIN_SCALE) & 0xFF


def freq_byte(freq_code: int) -> int:
    """Source value is already <=255 -- a frequency code/index, not raw Hz [confirm]."""
    return freq_code & 0xFF


@dataclass
class ParametricPoint:
    freq_code: int
    gain_db: float
    q: float = 1.0


def posture_ctx(standing: bool = False, laying: bool = False, hanging: bool = False) -> int:
    """The `ctx` byte: 0 for the default/standing profile, else a posture bitfield
    (bit0 standing, bit1 laying, bit2 hanging)."""
    return (
        (0x01 if standing else 0)
        | (0x02 if laying else 0)
        | (0x04 if hanging else 0)
    )


@dataclass
class ParametricEqCurve:
    points: list[ParametricPoint] = field(default_factory=list)
    ctx: int = 0

    def encode(self, layout: str = "fixed10") -> bytes:
        """Serialise (CORE.md section 3.4).

          "fixed10"  [ctx, (gain, freq, q) x 10]              31 bytes
          "delta2b"  [ctx, maskHi, maskLo, (gain, freq) x n]  no Q byte
          "delta3b"  [ctx, maskHi, maskLo, (gain, freq, q) x n]

        The mask is BE16, bit i = point i. For the delta layouts, point `i` comes
        from `self.points[i]` and a point with `gain_db is None` is treated as
        absent. "fixed10" pads/truncates to exactly 10 points.
        """
        if layout == "fixed10":
            out = bytearray([self.ctx & 0xFF])
            for k in range(10):
                if k < len(self.points):
                    p = self.points[k]
                    out += bytes(
                        [parametric_gain_byte(p.gain_db), freq_byte(p.freq_code), parametric_q_byte(p.q)]
                    )
                else:
                    out += bytes([parametric_gain_byte(0.0), 0, parametric_q_byte(0.0)])
            return bytes(out)

        if layout in ("delta2b", "delta3b"):
            mask = 0
            body = bytearray()
            for k, p in enumerate(self.points):
                if p is None or p.gain_db is None:
                    continue
                mask |= 1 << k
                body += bytes([parametric_gain_byte(p.gain_db), freq_byte(p.freq_code)])
                if layout == "delta3b":
                    body += bytes([parametric_q_byte(p.q)])
            return bytes([self.ctx & 0xFF, (mask >> 8) & 0xFF, mask & 0xFF]) + bytes(body)

        raise ValueError(f"unknown parametric layout {layout!r}")
