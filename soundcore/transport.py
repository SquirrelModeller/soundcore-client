"""RFCOMM transport for the accessory control channel (PROTOCOL.md section 1).

Linux only: uses the kernel Bluetooth sockets exposed by CPython
(`socket.AF_BLUETOOTH` + `BTPROTO_RFCOMM`). No external dependency.

The control endpoint is a vendor RFCOMM channel, *not* the SDP-advertised SPP
record. Channel 15 is the common one (17 seen on some units carrying a battery-only
stream). `probe_channel` scans for one that connects and answers a device-info
request.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Callable

from .commands import Commands
from .protocol import Frame, split_events

DEFAULT_CHANNELS = (15, 17, *range(1, 31))
_PROBE_TIMEOUT = 2.0


class RfcommTransport:
    """A framed connection to one device. Reads run on a background thread; each
    complete event frame is handed to `on_frame`."""

    def __init__(self, address: str, channel: int = 15):
        self.address = address
        self.channel = channel
        self._sock: socket.socket | None = None
        self._rx = bytearray()
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()
        self._send_lock = threading.Lock()
        self.on_frame: Callable[[Frame], None] | None = None
        self.on_disconnect: Callable[[Exception | None], None] | None = None

    # --- connection ------------------------------------------------------
    @staticmethod
    def _new_socket() -> socket.socket:
        if not hasattr(socket, "AF_BLUETOOTH"):
            raise RuntimeError("this Python build has no AF_BLUETOOTH support")
        return socket.socket(
            socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM
        )

    def connect(self, timeout: float = 10.0) -> None:
        sock = self._new_socket()
        sock.settimeout(timeout)
        sock.connect((self.address, self.channel))
        sock.settimeout(None)
        self._sock = sock
        self._stop.clear()
        self._reader = threading.Thread(
            target=self._read_loop, name=f"rfcomm-{self.address}", daemon=True
        )
        self._reader.start()

    @classmethod
    def probe_channel(
        cls, address: str, channels=DEFAULT_CHANNELS, timeout: float = _PROBE_TIMEOUT
    ) -> int:
        """Return the first channel that connects and answers request_device_info."""
        probe = Commands.request_device_info()
        for ch in channels:
            try:
                sock = cls._new_socket()
                sock.settimeout(timeout)
                sock.connect((address, ch))
                sock.sendall(probe)
                buf = bytearray()
                deadline = time.monotonic() + timeout
                answered = False
                while time.monotonic() < deadline:
                    try:
                        chunk = sock.recv(512)
                    except TimeoutError:
                        break
                    if not chunk:
                        break
                    buf += chunk
                    frames, rest = split_events(bytes(buf))
                    buf = bytearray(rest)
                    if any(f.group == 0x01 and f.command == 0x01 for f in frames):
                        answered = True
                        break
                sock.close()
                if answered:
                    return ch
            except (TimeoutError, OSError):
                continue
        raise ConnectionError(f"no responsive RFCOMM channel on {address}")

    def close(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._sock.close()
            self._sock = None

    @property
    def connected(self) -> bool:
        return self._sock is not None and not self._stop.is_set()

    # --- io -------------------------------------------------------------
    def send(self, frame: bytes) -> None:
        if self._sock is None:
            raise ConnectionError("not connected")
        with self._send_lock:
            self._sock.sendall(frame)

    def _read_loop(self) -> None:
        err: Exception | None = None
        sock = self._sock
        if sock is None:
            return
        try:
            while not self._stop.is_set():
                chunk = sock.recv(1024)
                if not chunk:
                    break
                self._rx += chunk
                frames, rest = split_events(bytes(self._rx))
                self._rx = bytearray(rest)
                for f in frames:
                    if self.on_frame is not None:
                        self.on_frame(f)
        except OSError as exc:
            err = exc
        finally:
            self._stop.set()
            if self.on_disconnect is not None:
                self.on_disconnect(err)
