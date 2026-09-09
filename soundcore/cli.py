"""Command-line entry point: `python -m soundcore ...`.

Subcommands:
  probe   <mac>                      find the control RFCOMM channel
  info    <mac> [--model M] [--ch N] request + decode the connect-time snapshot
  watch   <mac> [--ch N]             stream and pretty-print every inbound event
  send    <mac> <command> [args...]  build+send one command, print the reply
  decode  <hex>                      decode a captured frame offline (no radio)
"""

from __future__ import annotations

import argparse
import sys
import time

from . import __version__
from .commands import COMMAND_NAMES, Commands
from .deviceinfo import parse_device_info
from .events import parse_event
from .protocol import split_events


def _fmt(obj, indent=2):
    import pprint

    return pprint.pformat(obj, indent=indent, width=100, sort_dicts=True)


def _client(args):
    from .client import SoundcoreClient

    c = SoundcoreClient(args.mac, channel=getattr(args, "ch", None), model=getattr(args, "model", None))
    c.connect(probe=getattr(args, "ch", None) is None)
    return c


def cmd_probe(args) -> int:
    from .transport import RfcommTransport

    ch = RfcommTransport.probe_channel(args.mac)
    print(f"control channel: {ch}")
    return 0


def cmd_info(args) -> int:
    c = _client(args)
    try:
        info = c.get_device_info()
    finally:
        c.close()
    print(_fmt(info))
    return 0


def cmd_watch(args) -> int:
    c = _client(args)
    c.subscribe("*", lambda e: print(f"{e.name:<32} {_fmt(e.fields, indent=0)}"))
    print("watching -- ctrl-c to stop")
    try:
        while c.connected:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        c.close()
    return 0


def cmd_send(args) -> int:
    name = args.command
    if name not in COMMAND_NAMES and name != "raw":
        print(f"unknown command {name!r}. Known: {', '.join(COMMAND_NAMES)}", file=sys.stderr)
        return 2
    conv = [int(a, 0) if a.lstrip("-").isdigit() or a.startswith(("0x", "0X")) else a for a in args.args]
    frame = getattr(Commands, name)(*conv)
    print(f"tx: {frame.hex()}")
    c = _client(args)
    try:
        grp, cmdb = frame[5], frame[6]
        # the reply usually echoes the command byte with the high bit set;
        # a request_* keeps it clear -- try both.
        seen = []
        c.subscribe("*", seen.append)
        c.send(frame)
        time.sleep(args.timeout)
        matches = [e for e in seen if e.group == grp and e.command in (cmdb, cmdb | 0x80)]
        if matches:
            for e in matches:
                print(f"rx: {e.name} {_fmt(e.fields, indent=0)}")
        else:
            print(f"rx: (no matching reply in {args.timeout}s; {len(seen)} other frame(s))")
    finally:
        c.close()
    return 0


def cmd_decode(args) -> int:
    data = bytes.fromhex(args.hex.replace(" ", ""))
    frames, rest = split_events(data)
    for f in frames:
        ev = parse_event(f)
        print(f"{f!r}")
        print(f"  -> {ev.name}: {_fmt(ev.fields, indent=0)}")
        if (f.group, f.command) == (0x01, 0x01):
            print("  device_info:", _fmt(parse_device_info(f, model=args.model)))
    if rest:
        print(f"trailing/incomplete: {rest.hex()}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="soundcore", description=__doc__)
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("probe")
    sp.add_argument("mac")
    sp.set_defaults(func=cmd_probe)

    sp = sub.add_parser("info")
    sp.add_argument("mac")
    sp.add_argument("--model")
    sp.add_argument("--ch", type=int)
    sp.set_defaults(func=cmd_info)

    sp = sub.add_parser("watch")
    sp.add_argument("mac")
    sp.add_argument("--ch", type=int)
    sp.add_argument("--model")
    sp.set_defaults(func=cmd_watch)

    sp = sub.add_parser("send")
    sp.add_argument("mac")
    sp.add_argument("command")
    sp.add_argument("args", nargs="*")
    sp.add_argument("--ch", type=int)
    sp.add_argument("--model")
    sp.add_argument("--timeout", type=float, default=2.0)
    sp.set_defaults(func=cmd_send)

    sp = sub.add_parser("decode")
    sp.add_argument("hex")
    sp.add_argument("--model")
    sp.set_defaults(func=cmd_decode)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
