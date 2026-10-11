"""A simulated battery, for trying the dashboard without hardware.

The simulator does not shortcut the decoder: it builds real 300-byte frames
(the encoders below are the mirror image of protocol.decode_*), cuts them into
notification-sized chunks and feeds them through the same FrameAssembler and
decoder as a real BMS would. The tests use the encoders for round trips.
"""
from __future__ import annotations

import asyncio
import datetime
import math
import random
import struct
from typing import Callable

from . import protocol

CELLS = 8
CAPACITY_AH = 280.0
# open-circuit voltage of one LiFePO4 cell by state of charge: (soc %, volts)
OCV = [(0, 2.60), (3, 2.95), (8, 3.10), (15, 3.20), (30, 3.26), (50, 3.29), (70, 3.31),
       (90, 3.335), (96, 3.36), (99, 3.42), (100, 3.47)]


def _frame(kind: int) -> bytearray:
    frame = bytearray(protocol.FRAME_LEN)
    frame[0:4] = protocol.FRAME_HEADER
    frame[4] = kind
    return frame


def _seal(frame: bytearray) -> bytes:
    frame[protocol.FRAME_LEN - 1] = protocol.checksum(frame[:protocol.FRAME_LEN - 1])
    return bytes(frame)


def encode_cell_data(cells: list[float], current: float, soc: int, *, resistances: list[float] | None = None,
                     mos_temp: float = 25.0, temp1: float = 20.0, temp2: float = 20.0,
                     remain_ah: float = 0.0, nominal_ah: float = CAPACITY_AH, cycles: int = 0,
                     cycled_ah: float = 0.0, soh: int = 100, runtime_s: int = 0,
                     balance_action: int = 0, balance_current: float = 0.0, alarms: int = 0,
                     mos_charge: bool = True, mos_discharge: bool = True, counter: int = 0) -> bytes:
    """Build a frame of type 0x02 from the given values."""
    f = _frame(protocol.FRAME_CELL_DATA)
    f[5] = counter & 0xFF
    for i, v in enumerate(cells):
        struct.pack_into("<H", f, 6 + i * 2, round(v * 1000))
    struct.pack_into("<I", f, 70, (1 << len(cells)) - 1)                 # enabled cells bitmask
    struct.pack_into("<H", f, 74, round(sum(cells) / len(cells) * 1000))
    struct.pack_into("<H", f, 76, round((max(cells) - min(cells)) * 1000))
    f[78] = cells.index(max(cells))
    f[79] = cells.index(min(cells))
    for i, r in enumerate(resistances or [0.05] * len(cells)):
        struct.pack_into("<H", f, 80 + i * 2, round(r * 1000))
    total = sum(cells)
    struct.pack_into("<h", f, 144, round(mos_temp * 10))
    struct.pack_into("<I", f, 150, round(total * 1000))
    struct.pack_into("<I", f, 154, round(abs(total * current) * 1000))   # power is sent unsigned
    struct.pack_into("<i", f, 158, round(current * 1000))
    struct.pack_into("<h", f, 162, round(temp1 * 10))
    struct.pack_into("<h", f, 164, round(temp2 * 10))
    struct.pack_into("<I", f, 166, alarms)
    struct.pack_into("<h", f, 170, round(balance_current * 1000))
    f[172] = balance_action
    f[173] = soc
    struct.pack_into("<I", f, 174, round(remain_ah * 1000))
    struct.pack_into("<I", f, 178, round(nominal_ah * 1000))
    struct.pack_into("<I", f, 182, cycles)
    struct.pack_into("<I", f, 186, round(cycled_ah * 1000))
    f[190] = soh
    struct.pack_into("<I", f, 194, runtime_s)
    f[198] = int(mos_charge)
    f[199] = int(mos_discharge)
    return _seal(f)


def encode_settings(values: dict) -> bytes:
    """Build a frame of type 0x01 from a dict shaped like protocol.decode_settings()."""
    f = _frame(protocol.FRAME_SETTINGS)
    millis = {"cell_uvp": 10, "cell_uvpr": 14, "cell_ovp": 18, "cell_ovpr": 22, "soc100_v": 30, "soc0_v": 34,
              "rcv_v": 38, "rfv_v": 42, "power_off_v": 46, "max_charge_a": 50, "max_discharge_a": 62,
              "max_balance_a": 78, "capacity_ah": 130, "balance_start_v": 138}
    plain = {"balance_delta_mv": 26, "charge_ocp_delay": 54, "discharge_ocp_delay": 66, "cell_count": 114,
             "charge_switch": 118, "discharge_switch": 122, "balancer_switch": 126}
    for key, offset in millis.items():
        struct.pack_into("<I", f, offset, round(values[key] * 1000))
    for key, offset in plain.items():
        struct.pack_into("<I", f, offset, int(values[key]))
    return _seal(f)


def encode_device_info(values: dict) -> bytes:
    """Build a frame of type 0x03 from a dict shaped like protocol.decode_device_info()."""
    f = _frame(protocol.FRAME_DEVICE_INFO)
    for key, (start, end) in {"vendor": (6, 22), "hw_version": (22, 30), "sw_version": (30, 38),
                              "name": (46, 62), "mfg_date": (78, 86), "serial": (86, 102)}.items():
        raw = values.get(key, "").encode("ascii")[:end - start]
        f[start:start + len(raw)] = raw
    return _seal(f)


DEMO_SETTINGS = {
    "cell_uvp": 2.6, "cell_uvpr": 2.8, "cell_ovp": 3.6, "cell_ovpr": 3.4, "balance_delta_mv": 10,
    "soc100_v": 3.445, "soc0_v": 2.7, "rcv_v": 3.45, "rfv_v": 3.35, "power_off_v": 2.4,
    "max_charge_a": 100.0, "charge_ocp_delay": 10, "max_discharge_a": 150.0, "discharge_ocp_delay": 10,
    "max_balance_a": 2.0, "cell_count": CELLS, "charge_switch": True, "discharge_switch": True,
    "balancer_switch": True, "capacity_ah": CAPACITY_AH, "balance_start_v": 3.4,
}
DEMO_DEVICE = {"vendor": "JK_DEMO_8S", "hw_version": "19A", "sw_version": "19.10",
               "name": "Demo battery", "mfg_date": "260101", "serial": "DEMO00000001"}


def _ocv(soc: float) -> float:
    for (s0, v0), (s1, v1) in zip(OCV, OCV[1:]):
        if soc <= s1:
            return v0 + (v1 - v0) * (soc - s0) / (s1 - s0)
    return OCV[-1][1]


class DemoBattery:
    """An 8-cell 280 Ah LiFePO4 pack on a small solar system: sun by day, a house load around the clock."""

    def __init__(self, seed: int = 7) -> None:
        self.rng = random.Random(seed)
        self.soc = 55.0
        self.offsets = [self.rng.uniform(-0.003, 0.003) for _ in range(CELLS)]   # cells are never identical
        self.cloud = 0.8
        self.spike = 0.0
        self.cycled_ah = 4200.0
        self.resistances = [round(self.rng.uniform(0.046, 0.058), 3) for _ in range(CELLS)]
        self.counter = 0

    def net_power(self, when: datetime.datetime) -> float:
        """Watts into the battery (negative = out of it) at a given time of day."""
        hour = when.hour + when.minute / 60 + when.second / 3600
        self.cloud = min(1.0, max(0.25, self.cloud + self.rng.uniform(-0.03, 0.03)))
        sun = max(0.0, math.sin(math.pi * (hour - 6.5) / 11.0)) if 6.5 < hour < 17.5 else 0.0
        solar = 1500.0 * sun ** 1.3 * self.cloud
        load = 140.0 + 60.0 * self.rng.random()
        if 6.5 < hour < 8:
            load += 350
        if 17.5 < hour < 22:
            load += 280
        self.spike = max(0.0, self.spike - 300) if self.spike else (900.0 if self.rng.random() < 0.004 else 0.0)
        return solar - load - self.spike

    def step(self, when: datetime.datetime, dt_s: float) -> dict:
        """Advance the model by dt_s seconds; returns the values a BMS would measure."""
        power = self.net_power(when)
        if self.soc >= 100 and power > 0:
            power = 0.0                                  # full: the charger backs off
        if self.soc <= 8 and power < 0:
            power = 0.0                                  # empty: the inverter moves the house to the grid
        rest = _ocv(self.soc)
        current = power / (rest * CELLS)
        self.soc = min(100.0, max(0.0, self.soc + current * dt_s / 3600 / CAPACITY_AH * 100))
        self.cycled_ah += abs(current) * dt_s / 3600 / 2
        spread = 1.0 + max(0.0, self.soc - 94) * 1.5     # cells drift apart near the top
        cells = [round(rest + current * 0.0006 + o * spread + self.rng.uniform(-0.0005, 0.0005), 3)
                 for o in self.offsets]
        balancing = max(cells) - min(cells) > 0.010 and max(cells) > 3.4
        hour = when.hour + when.minute / 60
        ambient = 16 + 5 * math.sin(math.pi * (hour - 9) / 12)
        return {"cells": cells, "current": round(current, 3), "soc": round(self.soc),
                "mos_temp": round(ambient + 4 + abs(current) * 0.12, 1),
                "temp1": round(ambient + abs(current) * 0.03, 1), "temp2": round(ambient - 0.6 + abs(current) * 0.03, 1),
                "remain_ah": round(CAPACITY_AH * self.soc / 100, 2), "cycles": int(self.cycled_ah // CAPACITY_AH),
                "cycled_ah": round(self.cycled_ah, 1), "balance_action": 2 if balancing else 0,
                "balance_current": -0.6 if balancing else 0.0}

    def frame(self, values: dict, runtime_s: int) -> bytes:
        self.counter += 1
        return encode_cell_data(values["cells"], values["current"], values["soc"], resistances=self.resistances,
                                mos_temp=values["mos_temp"],
                                temp1=values["temp1"], temp2=values["temp2"], remain_ah=values["remain_ah"],
                                cycles=values["cycles"], cycled_ah=values["cycled_ah"],
                                balance_action=values["balance_action"], balance_current=values["balance_current"],
                                runtime_s=runtime_s, counter=self.counter)

    def history(self, hours: int = 24) -> list[dict]:
        """One point per minute for the past `hours`, so the chart is not empty at start."""
        now = datetime.datetime.now().replace(second=0, microsecond=0)
        points = []
        for minute in range(hours * 60, 0, -1):
            when = now - datetime.timedelta(minutes=minute)
            values = self.step(when, 60)
            total = sum(values["cells"])
            points.append({"t": when.isoformat(timespec="seconds"), "soc": values["soc"],
                           "voltage": round(total, 2), "current": round(values["current"], 2),
                           "power": round(total * values["current"], 1)})
        return points


async def run_demo(battery: DemoBattery, on_data: Callable[[str, dict], None],
                   on_state: Callable[[bool], None], stop: asyncio.Event) -> None:
    """Stand-in for JkBmsClient.run(): same callbacks, frames come from the simulator."""
    assembler = protocol.FrameAssembler()

    def deliver(frame: bytes) -> None:
        for start in range(0, len(frame), 128):                  # like BLE notifications
            for complete in assembler.feed(frame[start:start + 128]):
                kind, payload = protocol.decode(complete)
                if kind:
                    on_data(kind, payload)

    on_state(True)
    deliver(encode_device_info(DEMO_DEVICE))
    deliver(encode_settings(DEMO_SETTINGS))
    runtime = 86400 * 212
    while not stop.is_set():
        deliver(battery.frame(battery.step(datetime.datetime.now(), 1.0), runtime))
        runtime += 1
        try:
            await asyncio.wait_for(stop.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            pass
    on_state(False)


# ------------------------------------------------------------ demo sockets ---
class DemoPlug:
    """A pretend smart plug with the three calls SocketController uses."""

    class _Info:
        def __init__(self, on: bool) -> None:
            self.device_on = on

    def __init__(self) -> None:
        self.is_on = False
        self.broken = False          # tests flip this to simulate an expired session or a dead plug

    async def _check(self) -> None:
        if self.broken:
            raise ConnectionError("plug does not answer")

    async def on(self) -> None:
        await self._check()
        self.is_on = True

    async def off(self) -> None:
        await self._check()
        self.is_on = False

    async def get_device_info(self):
        await self._check()
        return self._Info(self.is_on)


def demo_connector(plugs: dict[str, DemoPlug] | None = None):
    """connect(ip) for SocketController that hands out DemoPlug objects, one per address."""
    plugs = {} if plugs is None else plugs

    async def connect(ip: str) -> DemoPlug:
        plug = plugs.setdefault(ip, DemoPlug())
        await plug._check()
        return plug
    return connect


DEMO_SOCKETS = {"on_soc": 50, "off_soc": 35, "check_interval": 5,
                "devices": [{"name": "Water heater", "ip": "demo-1"},
                            {"name": "Pool pump", "ip": "demo-2", "on_soc": 75, "off_soc": 60}]}
