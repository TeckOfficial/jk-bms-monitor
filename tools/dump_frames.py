#!/usr/bin/env python3
"""Connect to a JK BMS and print the raw frames it sends, as hex.

    python tools/dump_frames.py --address C8:47:80:xx:xx:xx
    python tools/dump_frames.py --address ... --seconds 30 --out frames.txt

Useful when a value looks wrong or your BMS model lays its frames out
differently: the dump plus what the vendor app shows at that moment is exactly
what is needed to find the right offsets.

PRIVACY: device info frames (type 03) contain the serial number and the
Bluetooth passcodes in clear text. They are left out unless you pass
--include-device-info. Do not post such a frame publicly.

Stop the monitor first: the BMS accepts only one Bluetooth connection.
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from jkbms import protocol                      # noqa: E402
from jkbms.client import JkBmsClient            # noqa: E402

NAMES = {protocol.FRAME_SETTINGS: "settings", protocol.FRAME_CELL_DATA: "cell_data",
         protocol.FRAME_DEVICE_INFO: "device_info"}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("-a", "--address", required=True, help="Bluetooth address of the BMS")
    parser.add_argument("--seconds", type=float, default=20, help="how long to listen (default 20)")
    parser.add_argument("--max-cell-frames", type=int, default=5, help="cell data frames to keep (default 5)")
    parser.add_argument("--include-device-info", action="store_true", help="also dump type 03 frames (serial, passcodes!)")
    parser.add_argument("--chunks", action="store_true",
                        help="also log every Bluetooth notification as received (includes device info, see PRIVACY)")
    parser.add_argument("--out", type=pathlib.Path, help="write to this file instead of the screen")
    args = parser.parse_args()

    lines: list[str] = []
    counts: dict[str, int] = {}
    started = asyncio.get_running_loop().time()

    def on_chunk(chunk: bytes) -> None:
        lines.append(f"chunk {asyncio.get_running_loop().time() - started:7.3f}s {len(chunk):3d} {chunk.hex()}")

    def on_raw(frame: bytes) -> None:
        kind = NAMES.get(frame[4], f"type_{frame[4]:02x}")
        counts[kind] = counts.get(kind, 0) + 1
        if kind == "device_info" and not args.include_device_info:
            return
        if kind == "cell_data" and counts[kind] > args.max_cell_frames:
            return
        lines.append(f"{kind} {frame.hex()}")

    stop = asyncio.Event()
    client = JkBmsClient(args.address, lambda kind, payload: None, on_raw=on_raw,
                         on_chunk=on_chunk if args.chunks else None,
                         log=lambda text: print(text, file=sys.stderr))
    task = asyncio.create_task(client.run(stop))
    await asyncio.sleep(args.seconds)
    stop.set()
    await task

    text = "\n".join(lines) + ("\n" if lines else "")
    if args.out:
        args.out.write_text(text)
    else:
        sys.stdout.write(text)
    print(f"frames seen: {counts or 'none'}; checksum errors: {client.checksum_errors}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
