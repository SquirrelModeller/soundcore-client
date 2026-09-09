"""Toggle noise cancelling.

    python examples/set_anc.py AA:BB:CC:DD:EE:FF nc|transparency|normal [level]
"""

import sys

from soundcore import AmbientMode, SoundcoreClient
from soundcore.commands import Commands

_MODES = {
    "nc": AmbientMode.NOISE_CANCELLING,
    "transparency": AmbientMode.TRANSPARENCY,
    "normal": AmbientMode.NORMAL,
}


def main() -> None:
    if len(sys.argv) < 3 or sys.argv[2] not in _MODES:
        print(__doc__)
        raise SystemExit(2)
    address, mode = sys.argv[1], _MODES[sys.argv[2]]
    level = int(sys.argv[3]) if len(sys.argv) > 3 else 2

    with SoundcoreClient(address) as c:
        c.send(Commands.set_ambient_mode(mode, nc_level=level, transparency_level=level))
        try:
            print(c.request(Commands.request_ambient_details(), expect=(0x06, 0x01), timeout=2.0).fields)
        except TimeoutError:
            print("sent (no confirmation frame seen)")


if __name__ == "__main__":
    main()
