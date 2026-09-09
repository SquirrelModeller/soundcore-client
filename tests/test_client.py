import threading
from collections.abc import Callable

from conftest import make_event_frame

from soundcore.client import SoundcoreClient
from soundcore.commands import Commands
from soundcore.protocol import Frame, split_events


class FakeTransport:
    """Stand-in for RfcommTransport: records sends, lets tests inject frames."""

    def __init__(self, address: str, channel: int) -> None:
        self.address = address
        self.channel = channel
        self.sent: list[bytes] = []
        self.on_frame: Callable[[Frame], None] | None = None
        self.on_disconnect: Callable[[Exception | None], None] | None = None
        self._connected = False

    def connect(self, timeout: float = 10.0) -> None:
        self._connected = True

    def close(self) -> None:
        self._connected = False
        if self.on_disconnect:
            self.on_disconnect(None)

    @property
    def connected(self) -> bool:
        return self._connected

    def send(self, frame: bytes) -> None:
        self.sent.append(frame)

    def feed(self, raw: bytes) -> None:
        assert self.on_frame is not None
        for f in split_events(raw)[0]:
            self.on_frame(f)


def _client(monkeypatch):
    import soundcore.client as mod

    holder = {}

    def factory(address, channel):
        holder["t"] = FakeTransport(address, channel)
        return holder["t"]

    monkeypatch.setattr(mod, "RfcommTransport", factory)
    c = SoundcoreClient("AA:BB:CC:DD:EE:FF", channel=15, model="a6610")
    c.connect(probe=False)
    return c, holder["t"]


def test_send_goes_through_transport(monkeypatch):
    c, t = _client(monkeypatch)
    c.send(Commands.set_volume(9))
    assert t.sent and t.sent[0][5:7] == bytes([0x01, 0x88])


def test_request_resolves_on_matching_opcode(monkeypatch):
    c, t = _client(monkeypatch)
    reply = make_event_frame(0x02, 0x01, bytes([0, 0xFE, 0]) + bytes([120] * 11))

    def responder():
        t.feed(reply)

    threading.Timer(0.05, responder).start()
    ev = c.request(Commands.request_eq(), expect=(0x02, 0x01), timeout=2.0)
    assert ev.name == "eq_reply"
    assert ev.fields["eq_type"] == "custom"


def test_subscribe_receives_events(monkeypatch):
    c, t = _client(monkeypatch)
    seen = []
    c.subscribe("battery_changed", seen.append)
    t.feed(make_event_frame(0x01, 0x03, bytes([5, 5, 5, 0])))
    assert seen and seen[0].fields["left_battery"] == 5
    assert c.state.left_battery == 5


def test_wildcard_subscription(monkeypatch):
    c, t = _client(monkeypatch)
    seen = []
    c.subscribe("*", seen.append)
    t.feed(make_event_frame(0x01, 0x04, bytes([1, 0, 0])))
    assert [e.name for e in seen] == ["charging_changed"]


def test_request_timeout(monkeypatch):
    c, t = _client(monkeypatch)
    import pytest

    with pytest.raises(TimeoutError):
        c.request(Commands.get_battery(), expect=(0x01, 0x03), timeout=0.1)


def test_get_device_info_parses_snapshot(monkeypatch):
    c, t = _client(monkeypatch)
    p = bytearray(79)
    p[2], p[3] = 6, 6
    p[16:32] = b"ABCDEF0123456789"
    p[32], p[33] = 2, 0xFE
    p[34:44] = bytes([120] * 10)
    snap = make_event_frame(0x01, 0x01, bytes(p))
    threading.Timer(0.05, lambda: t.feed(snap)).start()
    info = c.get_device_info(timeout=2.0)
    assert info.serial == "ABCDEF0123456789"
    assert c.state.device_info is info
