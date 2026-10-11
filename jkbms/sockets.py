"""Optional: switch TP-Link Tapo smart plugs by the battery's state of charge.

A plug in automatic mode is turned on when the state of charge reaches
`on_soc` and off when it falls to `off_soc`; in between it keeps its state.
Typical use: run a water heater, a pump or a dehumidifier only on surplus
solar energy.

The feature is off unless config.json has a "sockets" section (see README).
It needs the `tapo` package (pip install tapo) and the e-mail and password of
your TP-Link account, which the plugs require even for local control.

Safety rules built in:
* nothing is switched before fresh data has arrived from the BMS,
* if the BMS stays silent for `bms_stale_min` minutes, automatic plugs are
  turned off and stay off until data flows again (without this a plug would
  keep draining the battery on the last state of charge it knew),
* a plug in manual mode is never touched by the automation,
* on exit the plugs are left as they are.
"""
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable

CONNECT_TIMEOUT_S = 12
RETRY_S = (30, 60, 120, 300, 600)      # pause before the next attempt on an unreachable plug


class SocketError(Exception):
    """Raised by the manual actions; the message is safe to show to the user."""


def tapo_connector(email: str, password: str) -> Callable[[str], Awaitable[object]]:
    """Returns connect(ip) -> device with async on(), off() and get_device_info()."""
    async def connect(ip: str):
        from tapo import ApiClient                # imported late: only needed when sockets are used
        return await ApiClient(email, password).p100(ip)
    return connect


class _Socket:
    def __init__(self, ident: str, name: str, ip: str, on_soc: float, off_soc: float) -> None:
        self.id, self.name, self.ip = ident, name, ip
        self.on_soc, self.off_soc = on_soc, off_soc
        self.device = None
        self.on: bool | None = None
        self.mode = "auto"                        # "auto" | "manual"
        self.reason: str | None = None            # why it is on: "soc" | "manual"
        self.connected = False
        self.bms_stale = False
        self.fails = 0
        self.retry_at = 0.0
        self.lock = asyncio.Lock()                # automation and manual actions must not interleave

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "on": self.on, "mode": self.mode, "reason": self.reason,
                "connected": self.connected, "bms_stale": self.bms_stale,
                "on_soc": self.on_soc, "off_soc": self.off_soc}


class SocketController:
    """config: the "sockets" section of config.json.
    read_battery() -> (state of charge or None, age of that value in seconds or None)."""

    def __init__(self, config: dict, read_battery: Callable[[], tuple[float | None, float | None]], *,
                 connect: Callable[[str], Awaitable[object]] | None = None,
                 log: Callable[[str], None] = print, clock: Callable[[], float] = time.monotonic) -> None:
        self.read_battery = read_battery
        self.log, self.clock = log, clock
        self.interval = max(5.0, float(config.get("check_interval", 30)))
        self.stale_s = max(0.0, float(config.get("bms_stale_min", 10))) * 60
        on_soc, off_soc = float(config.get("on_soc", 95)), float(config.get("off_soc", 90))
        self.sockets: list[_Socket] = []
        for number, item in enumerate(config.get("devices", []), 1):
            if not item.get("ip"):
                continue
            s_on, s_off = float(item.get("on_soc", on_soc)), float(item.get("off_soc", off_soc))
            if s_off >= s_on:
                raise ValueError(f"socket {item.get('name', number)}: off_soc must be lower than on_soc")
            self.sockets.append(_Socket(f"s{number}", str(item.get("name") or f"Socket {number}"), item["ip"], s_on, s_off))
        self.connect = connect or tapo_connector(config.get("tapo_email", ""), config.get("tapo_password", ""))
        self._stale_logged = False
        self._started = self.clock()

    @property
    def enabled(self) -> bool:
        return bool(self.sockets)

    def snapshot(self) -> dict:
        return {"enabled": self.enabled, "check_interval": self.interval,
                "devices": [s.public() for s in self.sockets]}

    def _find(self, ident: str) -> _Socket:
        for s in self.sockets:
            if s.id == ident:
                return s
        raise SocketError("no such socket")

    # ---------------------------------------------------------- connection ---
    async def _ensure_connected(self, s: _Socket, force: bool = False) -> bool:
        """Connect if needed. An unreachable plug is retried with growing pauses, logged once."""
        if s.device is not None:
            return True
        if not force and self.clock() < s.retry_at:
            return False
        try:
            async def attempt():
                device = await self.connect(s.ip)
                return device, bool((await device.get_device_info()).device_on)
            s.device, s.on = await asyncio.wait_for(attempt(), timeout=CONNECT_TIMEOUT_S)
        except Exception as exc:
            delay = RETRY_S[min(s.fails, len(RETRY_S) - 1)]
            if s.fails == 0:
                why = "no answer" if isinstance(exc, asyncio.TimeoutError) else str(exc)[:120]
                self.log(f"socket {s.name} ({s.ip}) unreachable: {why}; retrying every {RETRY_S[0]} s to {RETRY_S[-1] // 60} min")
            s.fails += 1
            s.retry_at = self.clock() + delay
            s.device, s.connected, s.on = None, False, None
            return False
        if s.fails:
            self.log(f"socket {s.name} ({s.ip}) is back after {s.fails} failed attempts")
        self.log(f"socket {s.name} connected ({s.ip}), currently {'on' if s.on else 'off'}")
        s.fails, s.retry_at, s.connected = 0, 0.0, True
        return True

    async def _set(self, s: _Socket, on: bool) -> None:
        await (s.device.on() if on else s.device.off())
        s.on = on

    def _drop(self, s: _Socket) -> None:
        s.device, s.connected = None, False

    # ---------------------------------------------------------- automation ---
    async def step(self) -> None:
        """One pass over all sockets. Called every `check_interval` seconds by run()."""
        soc, age = self.read_battery()
        if age is None:                           # nothing from the BMS yet: count from our own start
            age = self.clock() - self._started
        stale = self.stale_s > 0 and age > self.stale_s
        if stale and not self._stale_logged:
            self.log(f"sockets: no BMS data for {age / 60:.0f} min, turning automatic sockets off until it returns")
        elif not stale and self._stale_logged:
            self.log("sockets: BMS data is back, automation continues")
        self._stale_logged = stale

        for s in self.sockets:
            async with s.lock:
                s.bms_stale = stale
                if not await self._ensure_connected(s):
                    continue
                try:
                    # also keeps the session alive and notices a plug switched by hand or in the Tapo app
                    s.on = bool((await s.device.get_device_info()).device_on)
                    if s.mode == "manual":
                        continue
                    if stale:
                        if s.on:
                            await self._set(s, False)
                            s.reason = None
                            self.log(f"socket {s.name} OFF (failsafe: BMS data {age / 60:.0f} min old)")
                        continue
                    if soc is None:
                        continue
                    if not s.on and soc >= s.on_soc:
                        await self._set(s, True)
                        s.reason = "soc"
                        self.log(f"socket {s.name} ON (state of charge {soc:.0f} % >= {s.on_soc:.0f} %)")
                    elif s.on and soc <= s.off_soc:
                        await self._set(s, False)
                        s.reason = None
                        self.log(f"socket {s.name} OFF (state of charge {soc:.0f} % <= {s.off_soc:.0f} %)")
                except Exception as exc:
                    self.log(f"socket {s.name}: {str(exc)[:120]}; reconnecting")
                    self._drop(s)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.step()
            except Exception as exc:              # never let one bad pass end the automation
                self.log(f"sockets: {exc}")
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                pass

    # ------------------------------------------------------ manual actions ---
    def set_mode(self, ident: str, mode: str) -> dict:
        s = self._find(ident)
        if mode not in ("auto", "manual"):
            raise SocketError("mode must be auto or manual")
        s.mode = mode
        s.reason = "manual" if (mode == "manual" and s.on) else None
        return s.public()

    async def switch(self, ident: str, on: bool) -> dict:
        """Manual on/off from the dashboard; puts the socket into manual mode.

        The plug's login expires after a few idle hours, so on an error the
        connection is rebuilt once and the action repeated.
        """
        s = self._find(ident)
        async with s.lock:
            error = "socket does not answer"
            for _attempt in (1, 2):
                if not await self._ensure_connected(s, force=True):
                    break
                try:
                    await self._set(s, on)
                    s.mode, s.reason = "manual", ("manual" if on else None)
                    return s.public()
                except Exception as exc:
                    error = str(exc)[:120]
                    self._drop(s)
            raise SocketError(error)
