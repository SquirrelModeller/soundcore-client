"""Independent, interoperable client for Soundcore-family Bluetooth accessories.

Clean-room implementation from PROTOCOL.md + the OPCODES / COMMANDS / EVENTS /
DEVICE-INFO catalogues (see PROVENANCE.md). No vendor code.

    from soundcore import SoundcoreClient, Commands, AmbientMode

    with SoundcoreClient("AA:BB:CC:DD:EE:FF", model="a6610") as c:
        print(c.get_device_info())
        c.send(Commands.set_ambient_mode(AmbientMode.NOISE_CANCELLING, nc_level=2))
"""

from .client import SoundcoreClient
from .commands import COMMAND_NAMES, Commands
from .deviceinfo import DeviceInfo, parse_device_info
from .events import EVENT_NAMES, ParsedEvent, parse_event
from .protocol import (
    AmbientMode,
    Frame,
    GraphicEqCurve,
    Group,
    ParametricEqCurve,
    ParametricPoint,
    Posture,
    TouchGesture,
    build_command,
    checksum,
    split_events,
)
from .state import DeviceState
from .transport import RfcommTransport

__version__ = "0.1.0"

__all__ = [
    "COMMAND_NAMES",
    "EVENT_NAMES",
    "AmbientMode",
    "Commands",
    "DeviceInfo",
    "DeviceState",
    "Frame",
    "GraphicEqCurve",
    "Group",
    "ParametricEqCurve",
    "ParametricPoint",
    "ParsedEvent",
    "Posture",
    "RfcommTransport",
    "SoundcoreClient",
    "TouchGesture",
    "build_command",
    "checksum",
    "parse_device_info",
    "parse_event",
    "split_events",
]
