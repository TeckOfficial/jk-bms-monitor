"""JK BMS Bluetooth protocol: frame assembly and decoding.

This module is pure Python with no I/O, so it can be reused on its own
(another transport, another UI, offline analysis of captured frames).

Covers the "JK02" protocol with the 32-cell frame layout, as spoken by the
JK-B2A20S20P (hardware 19, firmware 19.x) this project was developed against.
See docs/PROTOCOL.md for the full byte layout and for which fields were
verified on real hardware.

Quick tour
----------
* The BMS exposes one GATT characteristic (CHAR_UUID) used for both
  directions: commands are written to it, data arrives as notifications.
* A command is a 20-byte packet built by build_command().
* Data arrives as 300-byte frames split across several notifications.
  FrameAssembler glues the chunks back together and checks the checksum.
* decode() turns a frame into ("cell_data" | "settings" | "device_info", dict).
"""
from __future__ import annotations

import struct

SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

FRAME_HEADER = bytes((0x55, 0xAA, 0xEB, 0x90))
FRAME_LEN = 300                      # header .. checksum byte at index 299
FRAME_SETTINGS = 0x01
FRAME_CELL_DATA = 0x02
FRAME_DEVICE_INFO = 0x03

COMMAND_HEADER = bytes((0xAA, 0x55, 0x90, 0xEB))
COMMAND_LEN = 20
CMD_CELL_INFO = 0x96                 # answers with a settings frame, then streams cell data
CMD_DEVICE_INFO = 0x97               # answers with a device info frame

KEEPALIVE = b"AT\r\n"                # the module sends this now and then; not part of a frame

MAX_CELLS = 32


def checksum(data: bytes | bytearray) -> int:
    """8-bit sum of all bytes."""
    return sum(data) & 0xFF


def build_command(command: int) -> bytes:
    """20-byte command packet: AA 55 90 EB, command, 14 zero bytes, checksum."""
    packet = bytearray(COMMAND_LEN)
    packet[0:4] = COMMAND_HEADER
    packet[4] = command & 0xFF
    packet[19] = checksum(packet[:19])
    return bytes(packet)


class FrameAssembler:
    """Rebuilds 300-byte frames from BLE notification chunks.

    The notifications are treated as one byte stream: a frame starts at the
    header 55 AA EB 90 wherever that falls inside a notification, runs for 300
    bytes and ends with the checksum of the first 299. Anything between frames
    (padding, the module's "AT" keep-alives) is skipped. A frame that fails the
    checksum is counted in `checksum_errors` and the search continues right
    behind its header, so a torn frame costs one frame, not two.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()
        self.checksum_errors = 0

    def feed(self, chunk: bytes | bytearray) -> list[bytes]:
        """Add one notification; return the frames it completed (usually 0 or 1)."""
        if chunk and bytes(chunk) == KEEPALIVE * (len(chunk) // len(KEEPALIVE)):
            return []                   # one or more keep-alives and nothing else
        if chunk[:4] == FRAME_HEADER:
            self._buffer.clear()        # a notification that begins with a header always begins a frame
        self._buffer.extend(chunk)
        frames = []
        while True:
            start = self._buffer.find(FRAME_HEADER)
            if start < 0:
                # keep the tail: a header may be split between two notifications
                del self._buffer[:max(0, len(self._buffer) - (len(FRAME_HEADER) - 1))]
                break
            del self._buffer[:start]
            if len(self._buffer) < FRAME_LEN:
                break
            frame = bytes(self._buffer[:FRAME_LEN])
            if checksum(frame[:FRAME_LEN - 1]) == frame[FRAME_LEN - 1]:
                frames.append(frame)
                del self._buffer[:FRAME_LEN]
            else:
                self.checksum_errors += 1
                del self._buffer[:len(FRAME_HEADER)]     # resynchronise on the next header
        return frames


def _u16(frame: bytes, offset: int) -> int:
    return struct.unpack_from("<H", frame, offset)[0]


def _i16(frame: bytes, offset: int) -> int:
    return struct.unpack_from("<h", frame, offset)[0]


def _u32(frame: bytes, offset: int) -> int:
    return struct.unpack_from("<I", frame, offset)[0]


def _i32(frame: bytes, offset: int) -> int:
    return struct.unpack_from("<i", frame, offset)[0]


def _text(frame: bytes, start: int, end: int) -> str:
    return frame[start:end].split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()


def decode_cell_data(frame: bytes) -> dict:
    """Frame type 0x02: live measurements.

    Returns {"cells": [...V], "resistances": [...ohm], "summary": {...}}.
    Current and power are positive while charging, negative while discharging.
    """
    cells = []
    for i in range(MAX_CELLS):
        mv = _u16(frame, 6 + i * 2)
        if mv > 0:                                   # unused cell slots read 0
            cells.append(round(mv / 1000.0, 3))
    resistances = [round(_u16(frame, 80 + i * 2) / 1000.0, 4) for i in range(len(cells))]

    current = _i32(frame, 158) / 1000.0
    power = _u32(frame, 154) / 1000.0                # the BMS reports it unsigned
    if current < 0:
        power = -power
    alarms = _u32(frame, 166)

    summary = {
        "total_voltage": round(_u32(frame, 150) / 1000.0, 3),
        "sum_cells": round(sum(cells), 3),
        "avg_voltage": round(_u16(frame, 74) / 1000.0, 3),
        "delta_mv": round(_u16(frame, 76), 1),
        # Index (from 0) of the highest and lowest cell. These, the average and the delta are the
        # BMS's own slowly updated statistics, so they can lag the per-cell values by a few mV.
        "max_cell_idx": frame[78],
        "min_cell_idx": frame[79],
        "current": round(current, 3),
        "power": round(power, 3),
        "soc": frame[173],
        "mos_temp": round(_i16(frame, 144) / 10.0, 1),
        "temp1": round(_i16(frame, 162) / 10.0, 1),
        "temp2": round(_i16(frame, 164) / 10.0, 1),
        "balance_action": frame[172],                # 0 off, 1 charging balance, 2 discharging balance
        "balance_current": round(_i16(frame, 170) / 1000.0, 3),
        "alarms_hex": f"0x{alarms:08X}",
        "alarm": alarms != 0,
        "remain_ah": round(_u32(frame, 174) / 1000.0, 2),
        "nominal_ah": round(_u32(frame, 178) / 1000.0, 1),
        "cycles": _u32(frame, 182),
        "cycled_ah": round(_u32(frame, 186) / 1000.0, 1),
        "soh": frame[190],
        "runtime_s": _u32(frame, 194),
        "mos_charge": bool(frame[198]),
        "mos_discharge": bool(frame[199]),
    }
    return {"cells": cells, "resistances": resistances, "summary": summary}


def decode_settings(frame: bytes) -> dict:
    """Frame type 0x01: protection and balancing settings stored in the BMS."""
    return {
        "cell_uvp": round(_u32(frame, 10) / 1000.0, 3),          # undervoltage protection [V]
        "cell_uvpr": round(_u32(frame, 14) / 1000.0, 3),         # ... recovery
        "cell_ovp": round(_u32(frame, 18) / 1000.0, 3),          # overvoltage protection [V]
        "cell_ovpr": round(_u32(frame, 22) / 1000.0, 3),         # ... recovery
        "balance_delta_mv": _u32(frame, 26),                     # balancer trigger difference [mV]
        "soc100_v": round(_u32(frame, 30) / 1000.0, 3),          # cell voltage treated as 100 %
        "soc0_v": round(_u32(frame, 34) / 1000.0, 3),            # cell voltage treated as 0 %
        "rcv_v": round(_u32(frame, 38) / 1000.0, 3),             # requested charge voltage
        "rfv_v": round(_u32(frame, 42) / 1000.0, 3),             # requested float voltage
        "power_off_v": round(_u32(frame, 46) / 1000.0, 3),       # BMS shuts itself down below this
        "max_charge_a": round(_u32(frame, 50) / 1000.0, 3),
        "charge_ocp_delay": _u32(frame, 54),                     # [s]
        "max_discharge_a": round(_u32(frame, 62) / 1000.0, 3),
        "discharge_ocp_delay": _u32(frame, 66),                  # [s]
        "max_balance_a": round(_u32(frame, 78) / 1000.0, 3),
        "cell_count": _u32(frame, 114),
        "charge_switch": bool(_u32(frame, 118)),
        "discharge_switch": bool(_u32(frame, 122)),
        "balancer_switch": bool(_u32(frame, 126)),
        "capacity_ah": round(_u32(frame, 130) / 1000.0, 3),
        "balance_start_v": round(_u32(frame, 138) / 1000.0, 3),  # balancer works above this cell voltage
    }


def decode_device_info(frame: bytes) -> dict:
    """Frame type 0x03: identification strings.

    The same frame also carries the Bluetooth passcodes in clear text
    (see docs/PROTOCOL.md). They are deliberately not decoded here.
    """
    return {
        "vendor": _text(frame, 6, 22),
        "hw_version": _text(frame, 22, 30),
        "sw_version": _text(frame, 30, 38),
        "name": _text(frame, 46, 62),
        "mfg_date": _text(frame, 78, 86),
        "serial": _text(frame, 86, 102),
    }


_DECODERS = {
    FRAME_CELL_DATA: ("cell_data", decode_cell_data),
    FRAME_SETTINGS: ("settings", decode_settings),
    FRAME_DEVICE_INFO: ("device_info", decode_device_info),
}


def decode(frame: bytes) -> tuple[str | None, dict]:
    """Decode one complete frame. Unknown frame types give (None, {})."""
    if len(frame) < FRAME_LEN or frame[:4] != FRAME_HEADER:
        return None, {}
    kind = _DECODERS.get(frame[4])
    if kind is None:
        return None, {}
    return kind[0], kind[1](frame)
