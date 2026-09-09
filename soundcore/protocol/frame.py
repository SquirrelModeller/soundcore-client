"""Frame codec for the checksummed common accessory stack.

Implements PROTOCOL.md sections 2, 3, 5 and CORE.md section 1:

  command frame (host -> device):
      08 EE 00 00 <route> <group> <command> <len_lo> <len_hi> <payload...> <cksum>
  event frame (device -> host):
      09 FF 00 00 01 <group> <command> <len_lo> <len_hi> <payload...> <cksum>

`length` is a little-endian uint16 of the *whole* frame size (prefix + route/group/
command + the 2 length bytes + payload + the 1 checksum byte). `checksum` is the low
8 bits of the unsigned sum of every preceding byte.

Nothing in here is model-specific.
"""

from __future__ import annotations

from dataclasses import dataclass

COMMAND_PREFIX = bytes([0x08, 0xEE, 0x00, 0x00])
EVENT_PREFIX = bytes([0x09, 0xFF, 0x00, 0x00, 0x01])

# route byte: 0x00 for everything except group 0x07 / commands 0x8C..0x90
ROUTE_DEFAULT = 0x00
ROUTE_ALT = 0x10
_ROUTE_ALT_GROUP = 0x07
_ROUTE_ALT_COMMANDS = frozenset(range(0x8C, 0x91))  # 0x8C..0x90 inclusive

# framing variants (PROTOCOL.md section 10)
FRAMING_CHECKSUM = "checksum"
FRAMING_LEGACY = "legacy"

# header length that both framings share: 4-byte prefix + route + group + command
_CMD_HEADER_LEN = 7
_EVENT_HEADER_LEN = 9
_MIN_FRAME_LEN = 10  # empty payload, checksummed form


def route_for(group: int, command: int) -> int:
    """Return the route byte the given opcode is sent with."""
    if group == _ROUTE_ALT_GROUP and command in _ROUTE_ALT_COMMANDS:
        return ROUTE_ALT
    return ROUTE_DEFAULT


def checksum(data: bytes) -> int:
    """Low 8 bits of the unsigned sum of every byte in `data`."""
    return sum(data) & 0xFF


def build_command(
    group: int,
    command: int,
    payload: bytes = b"",
    *,
    route: int | None = None,
    framing: str = FRAMING_CHECKSUM,
) -> bytes:
    """Assemble a host -> device command frame.

    `route` defaults to `route_for(group, command)`. Pass it explicitly only to
    override the table (e.g. while probing an undocumented opcode).
    """
    if route is None:
        route = route_for(group, command)
    if not 0 <= group <= 0xFF or not 0 <= command <= 0xFF or not 0 <= route <= 0xFF:
        raise ValueError("group/command/route must be single bytes")

    head = COMMAND_PREFIX + bytes([route, group, command])

    if framing == FRAMING_CHECKSUM:
        total = _CMD_HEADER_LEN + 2 + len(payload) + 1
        body = head + bytes([total & 0xFF, (total >> 8) & 0xFF]) + payload
        return body + bytes([checksum(body)])
    if framing == FRAMING_LEGACY:
        total = _CMD_HEADER_LEN + 2 + len(payload)  # no trailing checksum
        return head + bytes([total & 0xFF, (total >> 8) & 0xFF]) + payload
    raise ValueError(f"unknown framing {framing!r}")


@dataclass(frozen=True)
class Frame:
    """A decoded device -> host event frame."""

    group: int
    command: int
    payload: bytes
    raw: bytes
    checksum_ok: bool

    @property
    def is_reply(self) -> bool:
        """True when the command byte has its high bit set.

        Note the device-info reply (0x01/0x01) keeps the high bit *clear* -- the
        device reuses the request code -- so this returns False for it.
        """
        return bool(self.command & 0x80)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        flag = "" if self.checksum_ok else " BADCKSUM"
        return (
            f"<Frame group=0x{self.group:02X} command=0x{self.command:02X} "
            f"payload={self.payload.hex()}{flag}>"
        )


def parse_frame(raw: bytes) -> Frame:
    """Decode a single, complete event frame. Does not validate the prefix length
    beyond what `split_events` already guarantees."""
    group = raw[5]
    command = raw[6]
    payload = raw[9:-1]
    ok = len(raw) >= 2 and checksum(raw[:-1]) == raw[-1]
    return Frame(group=group, command=command, payload=payload, raw=raw, checksum_ok=ok)


def split_events(buf: bytes) -> tuple[list[Frame], bytes]:
    """Split a receive buffer into complete event frames.

    Returns `(frames, remainder)`. `remainder` is the trailing bytes of an
    incomplete frame -- prepend it to the next read. Resyncs byte-by-byte on a
    bad prefix (PROTOCOL.md section 5).
    """
    frames: list[Frame] = []
    i = 0
    n = len(buf)
    while n - i >= _EVENT_HEADER_LEN:
        if buf[i] != 0x09 or buf[i + 1] != 0xFF:
            i += 1
            continue
        frame_len = buf[i + 7] | (buf[i + 8] << 8)
        if frame_len < _MIN_FRAME_LEN:
            # implausible length -- treat as desync, skip this byte
            i += 1
            continue
        if n - i < frame_len:
            break  # incomplete; keep from i onward
        frames.append(parse_frame(buf[i : i + frame_len]))
        i += frame_len
    return frames, buf[i:]
