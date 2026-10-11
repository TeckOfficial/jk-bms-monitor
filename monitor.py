#!/usr/bin/env python3
"""JK BMS Monitor: a small web dashboard for a JK BMS read over Bluetooth LE.

    python monitor.py --scan                      list nearby Bluetooth devices
    python monitor.py --address C8:47:80:xx:xx:xx connect to the BMS, serve the dashboard
    python monitor.py --demo                      simulated battery, no hardware needed

The dashboard is at http://<host>:8000. It has no login: keep the port inside
your home network.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from jkbms import __version__

BASE = pathlib.Path(__file__).resolve().parent
WEB = BASE / "web"

HISTORY_INTERVAL_S = 60          # one chart point per minute
HISTORY_HOURS = 24
HISTORY_SAVE_S = 300             # written to disk every 5 minutes (and on exit) to spare the SD card


class Monitor:
    """Holds everything the dashboard shows and keeps the 24-hour history."""

    def __init__(self, history_file: pathlib.Path | None, demo: bool = False) -> None:
        self.history_file = history_file
        self.state = {
            "version": __version__,
            "connected": False,
            "last_update": None,
            "demo": demo,
            "device": {}, "cells": [], "resistances": [], "summary": {}, "settings": {},
            "checksum_errors": 0,
            "peaks": {"charge_a": 0.0, "discharge_a": 0.0, "day": date.today().isoformat()},
            "sockets": {"enabled": False},
        }
        self.history: deque[dict] = deque(maxlen=HISTORY_HOURS * 60)
        self.last_data = None              # time.monotonic() of the last cell data frame
        self._last_point = 0.0
        self._last_save = time.time()
        self._load_history()

    # ------------------------------------------------------- BMS callbacks ---
    def on_state(self, connected: bool) -> None:
        self.state["connected"] = connected

    def on_data(self, kind: str, payload: dict) -> None:
        if kind == "device_info":
            self.state["device"] = payload
        elif kind == "settings":
            self.state["settings"] = payload
        elif kind == "cell_data":
            self.state["cells"] = payload["cells"]
            self.state["resistances"] = payload["resistances"]
            self.state["summary"] = summary = payload["summary"]
            self.state["last_update"] = datetime.now().isoformat()
            self.last_data = time.monotonic()
            self._track_peaks(summary["current"])
            self._track_history(summary)

    def battery(self) -> tuple[float | None, float | None]:
        """(state of charge, age of that value in seconds) for the socket automation."""
        if self.last_data is None:
            return None, None
        return self.state["summary"].get("soc"), time.monotonic() - self.last_data

    def _track_peaks(self, current: float) -> None:
        peaks, today = self.state["peaks"], date.today().isoformat()
        if peaks["day"] != today:
            peaks.update(day=today, charge_a=0.0, discharge_a=0.0)
        if current > 0.5:
            peaks["charge_a"] = max(peaks["charge_a"], round(current, 1))
        elif current < -0.5:
            peaks["discharge_a"] = max(peaks["discharge_a"], round(-current, 1))

    # ------------------------------------------------------------- history ---
    def _track_history(self, summary: dict) -> None:
        now = time.time()
        if now - self._last_point < HISTORY_INTERVAL_S:
            return
        self._last_point = now
        self.history.append({
            "t": datetime.now().isoformat(timespec="seconds"),
            "soc": summary["soc"],
            "voltage": round(summary["total_voltage"], 2),
            "current": round(summary["current"], 2),
            "power": round(summary["power"], 1),
        })
        if self.history_file and now - self._last_save >= HISTORY_SAVE_S:
            self._last_save = now
            snapshot = list(self.history)
            try:                                    # write in a thread, never block the event loop
                asyncio.get_running_loop().run_in_executor(None, self.save_history, snapshot)
            except RuntimeError:
                self.save_history(snapshot)

    def _load_history(self) -> None:
        if not self.history_file or not self.history_file.exists():
            return
        try:
            cutoff = (datetime.now() - timedelta(hours=HISTORY_HOURS)).isoformat()
            points = [p for p in json.loads(self.history_file.read_text()) if p.get("t", "") >= cutoff]
            self.history.extend(points)
            print(f"history: {len(points)} points loaded")
        except (OSError, ValueError) as exc:
            print(f"history could not be loaded: {exc}")

    def save_history(self, points: list[dict] | None = None) -> None:
        if not self.history_file:
            return
        try:
            tmp = self.history_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(list(self.history) if points is None else points, separators=(",", ":")))
            os.replace(tmp, self.history_file)
        except OSError as exc:
            print(f"history could not be saved: {exc}")


def create_app(address: str | None, demo: bool, history_file: pathlib.Path | None,
               sockets_config: dict | None = None) -> FastAPI:
    monitor = Monitor(None if demo else history_file, demo=demo)
    stop = asyncio.Event()

    sockets = None                     # optional automation of smart plugs, see jkbms/sockets.py
    if demo:
        from jkbms.demo import DEMO_SOCKETS, demo_connector
        from jkbms.sockets import SocketController
        sockets = SocketController(DEMO_SOCKETS, monitor.battery, connect=demo_connector())
    elif sockets_config and sockets_config.get("devices"):
        from jkbms.sockets import SocketController
        sockets = SocketController(sockets_config, monitor.battery)

    async def bms_task() -> None:
        """Run the BMS connection (or the simulator) and restart it if it ever crashes."""
        while not stop.is_set():
            try:
                if demo:
                    from jkbms.demo import DemoBattery, run_demo
                    battery = DemoBattery()
                    if not monitor.history:
                        monitor.history.extend(battery.history(HISTORY_HOURS))
                    await run_demo(battery, monitor.on_data, monitor.on_state, stop)
                else:
                    from jkbms.client import JkBmsClient
                    client = JkBmsClient(address, monitor.on_data, on_state=monitor.on_state)
                    monitor.client = client
                    await client.run(stop)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"BMS task crashed, restarting in 5 s: {exc}")
                monitor.on_state(False)
                await asyncio.sleep(5)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        tasks = [asyncio.create_task(bms_task())]
        if sockets is not None and sockets.enabled:
            tasks.append(asyncio.create_task(sockets.run(stop)))
        yield
        stop.set()
        for task in tasks:
            task.cancel()
            try:
                await task
            except (Exception, asyncio.CancelledError):
                pass
        monitor.save_history()

    app = FastAPI(title="JK BMS Monitor", lifespan=lifespan)
    app.state.monitor = monitor

    def snapshot() -> dict:
        client = getattr(monitor, "client", None)
        if client is not None:
            monitor.state["checksum_errors"] = client.checksum_errors
        if sockets is not None:
            monitor.state["sockets"] = sockets.snapshot()
        return monitor.state

    @app.get("/")
    async def index():
        return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/api/status")
    async def api_status():
        """Everything currently known about the battery, as one JSON object."""
        return snapshot()

    @app.get("/api/history")
    async def api_history(since: str = ""):
        """Chart points of the last 24 hours, one per minute.

        Without `since` the whole history; with `since=<ISO timestamp>` only newer
        points, so an open dashboard fetches a few bytes per minute, not 120 kB.
        """
        if not since:
            return {"full": True, "items": list(monitor.history)}
        return {"full": False, "items": [p for p in monitor.history if p.get("t", "") > since]}

    async def socket_action(action) -> JSONResponse | dict:
        from jkbms.sockets import SocketError
        if sockets is None or not sockets.enabled:
            return JSONResponse({"error": "sockets are not configured"}, 404)
        try:
            return {"ok": True, "socket": await action()}
        except SocketError as exc:
            return JSONResponse({"error": str(exc)}, 404 if "no such socket" in str(exc) else 400)

    @app.post("/api/sockets/{ident}/on")
    async def socket_on(ident: str):
        """Turn a socket on by hand; it switches to manual mode."""
        return await socket_action(lambda: sockets.switch(ident, True))

    @app.post("/api/sockets/{ident}/off")
    async def socket_off(ident: str):
        """Turn a socket off by hand; it switches to manual mode."""
        return await socket_action(lambda: sockets.switch(ident, False))

    @app.post("/api/sockets/{ident}/mode")
    async def socket_mode(ident: str, request: Request):
        """Body {"mode": "auto"} or {"mode": "manual"}."""
        body = await request.json()

        async def change():
            return sockets.set_mode(ident, str(body.get("mode", "")))
        return await socket_action(change)

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        """Live updates: once a second, only the top-level keys that changed."""
        await websocket.accept()
        sent: dict[str, str] = {}
        idle = 0
        try:
            while not stop.is_set():
                patch = {}
                for key, value in snapshot().items():
                    encoded = json.dumps(value, separators=(",", ":"), default=str)
                    if sent.get(key) != encoded:
                        sent[key] = encoded
                        patch[key] = value
                if patch:
                    idle = 0
                    await websocket.send_json(patch)
                else:
                    idle += 1
                    if idle >= 15:                  # keep-alive so proxies do not close a quiet socket
                        idle = 0
                        await websocket.send_json({})
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        except Exception:                           # the browser went away
            pass

    app.mount("/static", StaticFiles(directory=WEB), name="static")
    return app


def load_config(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise SystemExit(f"cannot read {path}: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Web dashboard for a JK BMS read over Bluetooth LE.")
    parser.add_argument("-a", "--address", help="Bluetooth address of the BMS (see --scan)")
    parser.add_argument("-c", "--config", type=pathlib.Path, default=BASE / "config.json",
                        help="JSON file with address/host/port (default: config.json next to this script)")
    parser.add_argument("--host", help="interface to listen on (default 0.0.0.0)")
    parser.add_argument("--port", type=int, help="HTTP port (default 8000)")
    parser.add_argument("--history-file", type=pathlib.Path, help="where the 24-hour chart is kept (default history.json)")
    parser.add_argument("--demo", action="store_true", help="simulated battery instead of Bluetooth")
    parser.add_argument("--scan", action="store_true", help="list nearby Bluetooth LE devices and exit")
    args = parser.parse_args()

    if args.scan:
        from jkbms.client import scan
        print("scanning for 8 seconds ...")
        for address, name, rssi, likely in asyncio.run(scan()):
            hint = "  <- looks like a JK BMS" if likely else ""
            print(f"  {address}  {rssi if rssi is not None else '?':>4} dBm  {name or '(no name)'}{hint}")
        print("A BMS is listed only while nothing is connected to it (close the vendor app, stop the monitor).")
        return

    config = load_config(args.config)
    address = args.address or os.environ.get("JKBMS_ADDRESS") or config.get("address")
    if not args.demo and not address:
        parser.error("no BMS address: use --address, the JKBMS_ADDRESS variable or config.json (or try --demo)")

    sockets_config = dict(config.get("sockets") or {})
    if sockets_config.get("devices") and not args.demo:
        sockets_config.setdefault("tapo_email", os.environ.get("TAPO_EMAIL", ""))
        sockets_config.setdefault("tapo_password", os.environ.get("TAPO_PASSWORD", ""))
        if not sockets_config["tapo_email"] or not sockets_config["tapo_password"]:
            parser.error('sockets need "tapo_email" and "tapo_password" in config.json (or TAPO_EMAIL / TAPO_PASSWORD)')
        try:
            import tapo  # noqa: F401
        except ImportError:
            parser.error("sockets need the tapo package: pip install tapo")

    import uvicorn
    app = create_app(address, args.demo, args.history_file or pathlib.Path(config.get("history_file", BASE / "history.json")),
                     sockets_config)
    uvicorn.run(app, host=args.host or config.get("host", "0.0.0.0"), port=args.port or int(config.get("port", 8000)))


if __name__ == "__main__":
    main()
