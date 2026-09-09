"""Shared test helpers."""

from __future__ import annotations


def make_event_frame(group: int, command: int, payload: bytes = b"") -> bytes:
    """Assemble a device -> host event frame the same way the device would:
    09 FF 00 00 01 <group> <command> <len_lo> <len_hi> <payload> <checksum>."""
    total = 9 + len(payload) + 1
    body = bytes([0x09, 0xFF, 0x00, 0x00, 0x01, group, command, total & 0xFF, (total >> 8) & 0xFF]) + payload
    return body + bytes([sum(body) & 0xFF])
