Frames captured on 2026-10-11 from a JK-B2A20S20P (hardware 19H, firmware 19.10,
8 LiFePO4 cells, 360 Ah) with `tools/dump_frames.py`. One frame per file, as hex.

- `cell_data.hex` – type `02`, battery charging at about 4.7 A, 39 %
- `settings.hex` – type `01`

Neither contains a serial number, a name or a passcode (those live in the
device info frame, type `03`, which is deliberately not included).
