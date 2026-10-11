"""Bluetooth connection to a JK BMS (via bleak): connect, start the data
stream, keep it alive, reconnect when it drops.

The BMS accepts a single Bluetooth connection at a time. While this client is
connected, the vendor's phone app cannot connect, and the other way round.
"""
from __future__ import annotations

import asyncio
import time
from typing import Callable

from bleak import BleakClient, BleakScanner

from . import protocol

SCAN_TIMEOUT_S = 15
CONNECT_TIMEOUT_S = 20
LOGIN_TIMEOUT_S = 30
RETRY_DELAY_S = 10
STALE_TIMEOUT_S = 60          # no notification for this long = dead link, reconnect
CELL_DATA_MIN_INTERVAL_S = 0.5


class JkBmsClient:
    """Keeps one BMS connected and hands decoded frames to callbacks.

    on_data(kind, payload)  kind is "cell_data", "settings" or "device_info"
    on_state(connected)     called when the link comes up or goes down
    on_raw(frame)           optional, every valid raw frame (for dump tools)

    Callbacks run inside the event loop, so keep them short.
    """

    def __init__(self, address: str, on_data: Callable[[str, dict], None], *,
                 on_state: Callable[[bool], None] | None = None,
                 on_raw: Callable[[bytes], None] | None = None,
                 on_chunk: Callable[[bytes], None] | None = None,
                 log: Callable[[str], None] = print) -> None:
        self.address = address
        self.on_data = on_data
        self.on_state = on_state or (lambda connected: None)
        self.on_raw = on_raw
        self.on_chunk = on_chunk          # every notification exactly as received (protocol debugging)
        self.log = log
        self.assembler = protocol.FrameAssembler()
        self._client: BleakClient | None = None
        self._last_notify = 0.0
        self._last_cell_data = 0.0
        self._have_device_info = False
        self._have_settings = False

    @property
    def checksum_errors(self) -> int:
        return self.assembler.checksum_errors

    # ------------------------------------------------------------ incoming ---
    def _on_notify(self, _sender, data: bytearray) -> None:
        try:
            if self.on_chunk:
                self.on_chunk(bytes(data))
            if not bytes(data).startswith(protocol.KEEPALIVE) or len(data) > 8:   # keep-alives alone do not prove the stream is alive
                self._last_notify = time.monotonic()
            for frame in self.assembler.feed(data):
                if self.on_raw:
                    self.on_raw(frame)
                kind, payload = protocol.decode(frame)
                if kind == "cell_data":
                    # the BMS streams several frames per second; two per second is plenty
                    now = time.monotonic()
                    if now - self._last_cell_data < CELL_DATA_MIN_INTERVAL_S:
                        continue
                    self._last_cell_data = now
                elif kind == "device_info":
                    self._have_device_info = True
                elif kind == "settings":
                    self._have_settings = True
                if kind:
                    self.on_data(kind, payload)
        except Exception as exc:                    # a bad frame must not kill the notify handler
            self.log(f"notify handler error: {exc}")

    # ------------------------------------------------------------ outgoing ---
    async def _send(self, command: int) -> None:
        await self._client.write_gatt_char(protocol.CHAR_UUID, protocol.build_command(command), response=False)

    async def _start_stream(self) -> None:
        """Subscribe and ask for device info, settings and the live stream.

        The sequence (including the initial 0x90 packet and the repeats) is the
        one that has been running reliably against real hardware. Requests are
        repeated because the BMS sometimes ignores the first one after connect.
        """
        await self._client.start_notify(protocol.CHAR_UUID, self._on_notify)
        await asyncio.sleep(1)
        await self._send(0x90)
        await asyncio.sleep(2)
        for _ in range(3):
            await self._send(protocol.CMD_DEVICE_INFO)
            await asyncio.sleep(2)
        for _ in range(3):
            await self._send(protocol.CMD_CELL_INFO)
            await asyncio.sleep(2)

    async def _disconnect(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass

    # ---------------------------------------------------------------- loop ---
    async def run(self, stop: asyncio.Event) -> None:
        """Connect and stay connected until `stop` is set."""
        async def pause(seconds: float) -> None:
            try:
                await asyncio.wait_for(stop.wait(), timeout=seconds)
            except asyncio.TimeoutError:
                pass

        while not stop.is_set():
            try:
                self.log(f"looking for BMS {self.address} ...")
                device = await BleakScanner.find_device_by_address(self.address, timeout=SCAN_TIMEOUT_S)
                if device is None:
                    self.log(f"BMS not found, retrying in {RETRY_DELAY_S} s")
                    await pause(RETRY_DELAY_S)
                    continue

                self._client = BleakClient(device)
                try:
                    await asyncio.wait_for(self._client.connect(), timeout=CONNECT_TIMEOUT_S)
                except asyncio.TimeoutError:
                    self.log("connect timed out")
                    await self._disconnect()
                    await pause(5)
                    continue
                if not self._client.is_connected:
                    self.log("connect failed")
                    await self._disconnect()
                    await pause(RETRY_DELAY_S)
                    continue

                self.log(f"connected to {device.name or self.address}")
                self._last_notify = time.monotonic()
                self._have_device_info = self._have_settings = False
                self.on_state(True)
                try:
                    await asyncio.wait_for(self._start_stream(), timeout=LOGIN_TIMEOUT_S)
                except asyncio.TimeoutError:
                    self.log("start of data stream timed out")
                    self.on_state(False)
                    await self._disconnect()
                    await pause(5)
                    continue

                self.log("receiving data")
                while self._client is not None and self._client.is_connected and not stop.is_set():
                    await pause(5)
                    if stop.is_set():
                        break
                    silent = time.monotonic() - self._last_notify
                    if silent > STALE_TIMEOUT_S:
                        self.log(f"no data for {silent:.0f} s, reconnecting")
                        break
                    try:
                        if not self._have_device_info:
                            await self._send(protocol.CMD_DEVICE_INFO)
                        if not self._have_settings:
                            await self._send(protocol.CMD_CELL_INFO)
                    except Exception:
                        break
            except asyncio.CancelledError:
                await self._disconnect()
                raise
            except Exception as exc:
                self.log(f"BMS error: {exc}")

            self.on_state(False)
            await self._disconnect()
            if not stop.is_set():
                await pause(RETRY_DELAY_S)


async def scan(timeout: float = 8.0) -> list[tuple[str, str, int | None, bool]]:
    """List nearby Bluetooth LE devices as (address, name, rssi, looks_like_jk), strongest first.

    The name is whatever is set in the vendor app: "JK-..." or "JK_..." on some
    units, a serial-like string on others, so it is only a hint. The second
    hint is the advertised 0xFFE0 service. A BMS that something is connected
    to does not advertise and will not be listed at all.
    """
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    out = []
    for device, adv in found.values():
        name = adv.local_name or device.name or ""
        likely = name.upper().startswith("JK") or protocol.SERVICE_UUID in [u.lower() for u in adv.service_uuids or []]
        out.append((device.address, name, adv.rssi, likely))
    out.sort(key=lambda item: item[2] if item[2] is not None else -999, reverse=True)
    return out
