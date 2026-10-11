# Changelog

## 1.0.0 – 2026-10-11

First public version.

- Reads a JK BMS over Bluetooth LE (JK02 protocol, 32-cell frame layout); tested on a JK-B2A20S20P, hardware 19H, firmware 19.10.
- Web dashboard: overview with a zoomable 24-hour chart, cells, system. English and Czech.
- JSON API and WebSocket updates.
- Optional: TP-Link Tapo smart plugs switched by state of charge.
- Demo mode with a simulated battery and plugs.
- `tools/dump_frames.py` for capturing raw frames.
- Protocol notes in `docs/PROTOCOL.md`.
