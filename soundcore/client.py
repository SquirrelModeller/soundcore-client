"""High-level client: transport + command builders + event parsing + state."""

from __future__ import annotations

import threading
from collections.abc import Callable

from .commands import Commands
from .deviceinfo import DeviceInfo, parse_device_info
from .events import ParsedEvent, parse_event
from .protocol import Frame
from .state import DeviceState
from .transport import RfcommTransport


class _Pending:
    __slots__ = ("event", "result")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.result: ParsedEvent | None = None


class SoundcoreClient:
    """Connect, send commands, receive parsed events.

        c = SoundcoreClient("AA:BB:CC:DD:EE:FF", model="a6610")
        c.connect()
        print(c.get_device_info())
        c.subscribe("battery_changed", lambda e: print(e.fields))
        c.send(Commands.set_ambient_mode(AmbientMode.NOISE_CANCELLING, nc_level=2))
    """

    cmd = Commands  # convenience handle: SoundcoreClient.cmd.set_volume(10)

    def __init__(self, address: str, *, channel: int | None = None, model: str | None = None):
        self.address = address
        self.channel = channel
        self.model = model
        self.state = DeviceState()
        self._transport: RfcommTransport | None = None
        self._subs: dict[str, list[Callable[[ParsedEvent], None]]] = {}
        self._any_subs: list[Callable[[ParsedEvent], None]] = []
        self._pending: dict[tuple[int, int], _Pending] = {}
        self._lock = threading.Lock()

    # --- lifecycle -----------------------------------------------------
    def connect(self, *, probe: bool = True, timeout: float = 10.0) -> None:
        ch = self.channel
        if ch is None:
            if not probe:
                raise ValueError("channel not set and probe=False")
            ch = RfcommTransport.probe_channel(self.address)
            self.channel = ch
        self._transport = RfcommTransport(self.address, ch)
        self._transport.on_frame = self._on_frame
        self._transport.on_disconnect = self._on_disconnect
        self._transport.connect(timeout=timeout)

    def close(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    def __enter__(self) -> SoundcoreClient:
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def connected(self) -> bool:
        return self._transport is not None and self._transport.connected

    # --- sending -----------------------------------------------------------
    def send(self, frame: bytes) -> None:
        if self._transport is None:
            raise ConnectionError("not connected")
        self._transport.send(frame)

    def request(
        self, frame: bytes, *, expect: tuple[int, int], timeout: float = 3.0
    ) -> ParsedEvent:
        """Send `frame` and block until an inbound frame with opcode `expect`
        arrives (or `timeout`). `expect` is `(group, command)` of the reply."""
        pending = _Pending()
        with self._lock:
            self._pending[expect] = pending
        try:
            self.send(frame)
            if not pending.event.wait(timeout):
                raise TimeoutError(f"no reply for opcode {expect} within {timeout}s")
            assert pending.result is not None
            return pending.result
        finally:
            with self._lock:
                self._pending.pop(expect, None)

    # --- convenience ----------------------------------------------------
    def get_device_info(self, *, timeout: float = 3.0) -> DeviceInfo:
        ev = self.request(Commands.request_device_info(), expect=(0x01, 0x01), timeout=timeout)
        info = parse_device_info(ev.frame, model=self.model)
        self.state.device_info = info
        return info

    def get_battery(self, *, timeout: float = 3.0) -> ParsedEvent:
        return self.request(Commands.get_battery(), expect=(0x01, 0x03), timeout=timeout)

    def get_ambient(self, *, timeout: float = 3.0) -> ParsedEvent:
        return self.request(Commands.request_ambient_details(), expect=(0x06, 0x01), timeout=timeout)

    def get_eq(self, *, timeout: float = 3.0) -> ParsedEvent:
        return self.request(Commands.request_eq(), expect=(0x02, 0x01), timeout=timeout)

    # --- subscriptions ----------------------------------------------------
    def subscribe(self, event_name: str, callback: Callable[[ParsedEvent], None]) -> None:
        """Call `callback(ParsedEvent)` for every matching event. Use "*" for all."""
        if event_name == "*":
            self._any_subs.append(callback)
        else:
            self._subs.setdefault(event_name, []).append(callback)

    def unsubscribe(self, event_name: str, callback: Callable[[ParsedEvent], None]) -> None:
        if event_name == "*":
            if callback in self._any_subs:
                self._any_subs.remove(callback)
        else:
            self._subs.get(event_name, []).remove(callback)

    # --- internals -------------------------------------------------------
    def _on_frame(self, frame: Frame) -> None:
        ev = parse_event(frame)
        try:
            self.state.apply(ev)
        except Exception:  # state folding must never kill the read loop
            pass

        with self._lock:
            pending = self._pending.get((frame.group, frame.command))
        if pending is not None:
            pending.result = ev
            pending.event.set()

        for cb in self._subs.get(ev.name, ()):
            _safe(cb, ev)
        for cb in self._any_subs:
            _safe(cb, ev)

    def _on_disconnect(self, err: Exception | None) -> None:
        with self._lock:
            pendings = list(self._pending.values())
            self._pending.clear()
        for p in pendings:
            p.event.set()  # unblock waiters; result stays None -> TimeoutError
        for cb in self._any_subs:
            _safe(cb, ParsedEvent("_disconnected", 0, 0, {"error": repr(err)}, Frame(0, 0, b"", b"", False)))


def _safe(cb: Callable[[ParsedEvent], object], ev: ParsedEvent) -> None:
    try:
        cb(ev)
    except Exception:
        pass
