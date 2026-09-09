"""Connect, print the snapshot, then follow live events for 30 s.

python examples/dump_state.py AA:BB:CC:DD:EE:FF [model]
"""

import sys
import time

from soundcore import SoundcoreClient
from soundcore.commands import Commands


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    address = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else None

    with SoundcoreClient(address, model=model) as c:
        print("channel:", c.channel)
        print("snapshot:", c.get_device_info())

        for opcode, builder in [
            ((0x01, 0x03), Commands.get_battery),
            ((0x06, 0x01), Commands.request_ambient_details),
            ((0x02, 0x01), Commands.request_eq),
        ]:
            try:
                ev = c.request(builder(), expect=opcode, timeout=2.0)
                print(f"{ev.name}: {ev.fields}")
            except TimeoutError:
                print(f"{opcode}: no reply")

        c.subscribe("*", lambda e: print("  event", e.name, e.fields))
        print("following events for 30 s ...")
        time.sleep(30)


if __name__ == "__main__":
    main()
