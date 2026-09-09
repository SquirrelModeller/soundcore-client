"""Connect-time snapshot decoding.

`parse_device_info(raw, model=...)` picks a per-model tail parser when one exists,
otherwise falls back to the stable leading blocks (FIX/BB) or the common TLV tag
catalogue. Pass the model code (e.g. "a6610") when you know it -- from the
BT name, an out-of-band lookup, or a prior capture.
"""

from __future__ import annotations

from ..protocol import Frame
from .common import DeviceInfo, decode_eq_index, iter_tlv, parse_leading_blocks, parse_tlv
from .models import BB_MODELS, TABULATED, TLV_MODELS

__all__ = [
    "TABULATED",
    "DeviceInfo",
    "decode_eq_index",
    "iter_tlv",
    "parse_device_info",
    "parse_leading_blocks",
    "parse_tlv",
]


def _looks_like_tlv(raw: bytes) -> bool:
    """Heuristic: a TLV snapshot starts with tag 0x01, len 0x01 at frame offset 9."""
    return len(raw) > 12 and raw[9] == 0x01 and raw[10] == 0x01


def parse_device_info(raw: bytes | Frame, *, model: str | None = None) -> DeviceInfo:
    if isinstance(raw, Frame):
        raw = raw.raw

    key = model.lower() if model else None

    if key and key in TABULATED:
        return TABULATED[key](raw)

    if (key and key in TLV_MODELS) or (key is None and _looks_like_tlv(raw)):
        return parse_tlv(raw, model=key)

    info = parse_leading_blocks(raw, model=key)
    if key and key in BB_MODELS:
        info.style = "BB"
    info.partial = True
    return info
