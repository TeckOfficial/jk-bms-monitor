# JK BMS Bluetooth protocol, as used by this project

Everything here describes what the code in `jkbms/protocol.py` does. It was
worked out and checked against one device:

| | |
|---|---|
| Model | JK-B2A20S20P (reports itself as `JK_B2A20S20P`) |
| Hardware / firmware | 19H / 19.10 |
| Pack | 8 × LiFePO4, 360 Ah |
| Host | Raspberry Pi Zero 2 W, Debian 13, BlueZ 5.82, bleak 3.0 |

Other JK models with the same "JK02, 32-cell" frame layout should work. Older
units use a 24-cell layout where everything after the cell voltages sits 16
bytes earlier; that layout is **not** implemented here.

The column **Checked** says how sure each field is:

- **yes** – confirmed on the device above by something independent of the field
  itself: another value in the same data (the cell voltages add up to the battery
  voltage, voltage × current gives the power, state of charge × capacity gives the
  remaining capacity, running time matches the manufacturing date …) or the
  settings known to be configured on that device,
- **plausible** – the value is sensible and stable on the device above, but
  nothing independent confirms it,
- **community** – taken from other open-source work (see the end), not checked here.

## Transport

| | |
|---|---|
| Service | `0000ffe0-0000-1000-8000-00805f9b34fb` |
| Characteristic | `0000ffe1-0000-1000-8000-00805f9b34fb` (write without response + notify) |
| Connections | one at a time: while a program is connected, the vendor app cannot connect |
| Pairing | none needed for reading |

Commands are written to the characteristic. Answers and the data stream arrive
as notifications on the same characteristic.

## Commands (host → BMS)

A command is always 20 bytes:

| Byte | Content |
|---|---|
| 0–3 | `AA 55 90 EB` |
| 4 | command code |
| 5–18 | zero for the read commands used here |
| 19 | checksum: sum of bytes 0–18, lowest 8 bits |

| Code | Meaning | Full packet |
|---|---|---|
| `0x97` | send device info | `aa5590eb97` + 14 × `00` + `11` |
| `0x96` | send settings once, then stream cell data | `aa5590eb96` + 14 × `00` + `10` |

The start sequence this project uses after subscribing to notifications:

1. wait 1 s, send `0x90`, wait 2 s
2. send `0x97` three times, 2 s apart
3. send `0x96` three times, 2 s apart
4. every 5 s re-send `0x97` / `0x96` until a device info frame / a settings frame has arrived

The `0x90` packet and the repeats come from the program this project grew out
of, which has been running this way since summer 2026. Whether `0x90` is needed was not tested;
it does no harm. Nothing is ever written to the BMS besides these three codes,
so no setting can be changed by this software.

## Frames (BMS → host)

A frame is 300 bytes:

| Byte | Content |
|---|---|
| 0–3 | `55 AA EB 90` |
| 4 | frame type: `01` settings, `02` cell data, `03` device info |
| 5 | frame counter |
| 6–298 | payload |
| 299 | checksum: sum of bytes 0–298, lowest 8 bits |

All multi-byte numbers are little-endian.

### How frames arrive

Observed on the device above (see `tools/dump_frames.py --chunks`):

- A cell data frame comes as three notifications of 128 + 128 + 48 bytes: the
  300 bytes of the frame and 4 more bytes behind it.
- Before the stream starts, the Bluetooth module sends the four bytes
  `41 54 0D 0A` (`AT\r\n`) about ten times a second, sometimes two in one
  notification. While the stream runs it still sends about one per frame.
- **A frame does not always start at the beginning of a notification.** The
  answers right after connecting come glued behind an `AT\r\n`
  (`41 54 0D 0A 55 AA EB 90 03 …`), and the settings answer is followed by the
  next frame without a break. An assembler that only looks for the header at the
  start of a notification loses those frames and counts checksum errors instead
  (four at every connect on the device above). `FrameAssembler` therefore treats
  the notifications as one byte stream and finds the header wherever it is.
- Once the stream runs, a cell data frame arrives about every 0.26 s. The client
  passes on at most two per second.

### Type `02` – cell data

| Offset | Type | Unit | Field | Checked |
|---|---|---|---|---|
| 6 + 2·n | u16 | mV | voltage of cell n (n = 0…31); 0 = slot unused | yes |
| 70 | u32 | bits | cells present (bit n = cell n) – `FF 00 00 00` for 8 cells | yes |
| 74 | u16 | mV | average cell voltage | yes |
| 76 | u16 | mV | difference between highest and lowest cell | yes |
| 78 | u8 | index from 0 | highest cell | yes |
| 79 | u8 | index from 0 | lowest cell | yes |
| 80 + 2·n | u16 | mΩ | resistance of the balance wire of cell n | plausible |
| 144 | i16 | 0.1 °C | MOSFET temperature | plausible |
| 146 | u32 | bits | wire resistance warnings | community |
| 150 | u32 | mV | battery voltage | yes |
| 154 | u32 | mW | power, **unsigned** | yes |
| 158 | i32 | mA | current, positive = charging | yes |
| 162 | i16 | 0.1 °C | temperature sensor 1 | plausible |
| 164 | i16 | 0.1 °C | temperature sensor 2 | plausible |
| 166 | u32 | bits | alarms (0 = none); the meaning of single bits is not decoded here | plausible |
| 170 | i16 | mA | balancing current | plausible |
| 172 | u8 | | balancer: 0 off, 1 charging, 2 discharging | plausible |
| 173 | u8 | % | state of charge | yes |
| 174 | u32 | mAh | remaining capacity | yes |
| 178 | u32 | mAh | nominal (full) capacity | yes |
| 182 | u32 | | cycle count | yes |
| 186 | u32 | mAh | total cycled capacity | yes |
| 190 | u8 | % | state of health | plausible |
| 191 | u8 | | precharge state | community |
| 194 | u32 | s | total running time | yes |
| 198 | u8 | | charging MOSFET on | yes |
| 199 | u8 | | discharging MOSFET on | yes |

Notes:

- Power is sent without a sign. The decoder gives it the sign of the current,
  so `power` is negative while discharging.
- Average, difference and the highest/lowest cell are the BMS's own statistics
  and change more slowly than the per-cell voltages. In consecutive frames the
  cell voltages jitter by a few mV while these four stay put, so the "highest
  cell" may briefly not be the highest of the values in the same frame.
- Bytes 200–298 contain more data (non-zero on the device above) that this
  project does not decode.

### Type `01` – settings

All fields are u32.

| Offset | Unit | Field | Value on the test device | Checked |
|---|---|---|---|---|
| 10 | mV | cell undervoltage protection | 2600 | yes |
| 14 | mV | … recovery | 2800 | yes |
| 18 | mV | cell overvoltage protection | 3600 | yes |
| 22 | mV | … recovery | 3400 | yes |
| 26 | mV | balancer trigger difference | 10 | yes |
| 30 | mV | cell voltage counted as 100 % | 3445 | yes |
| 34 | mV | cell voltage counted as 0 % | 2700 | yes |
| 38 | mV | requested charge voltage | 3450 | yes |
| 42 | mV | requested float voltage | 3350 | yes |
| 46 | mV | power-off voltage | 2400 | yes |
| 50 | mA | max charge current | 150000 | yes |
| 54 | s | charge overcurrent delay | 10 | plausible |
| 62 | mA | max discharge current | 200000 | yes |
| 66 | s | discharge overcurrent delay | 10 | plausible |
| 78 | mA | max balancing current | 2000 | yes |
| 114 | | cell count | 8 | yes |
| 118 | 0/1 | charging switch | 1 | yes |
| 122 | 0/1 | discharging switch | 1 | yes |
| 126 | 0/1 | balancer switch | 1 | yes |
| 130 | mAh | battery capacity | 360000 | yes |
| 138 | mV | balancer start voltage | 3400 | yes |

Offset 26 is easy to mistake for the balancer start voltage. It is the trigger
*difference*; the start voltage is at 138.

Other non-zero values in the settings frame of the test device, not decoded:
6 (3500), 58 (50), 70 (60), 74 (30), 82–110 (550, 500, 700, 600, 20, 50, 800,
700 – by their size most likely the temperature and short-circuit protection
limits), 134 (5).

### Type `03` – device info

| Offset | Length | Field | Checked |
|---|---|---|---|
| 6 | 16 | model, ASCII, zero padded | yes |
| 22 | 8 | hardware version | yes |
| 30 | 8 | firmware version | yes |
| 46 | 16 | device name (as set in the vendor app) | plausible |
| 62 | 16 | **Bluetooth passcode, clear text** | community |
| 78 | 8 | manufacturing date, `YYMMDD` | yes |
| 86 | 16 | serial number | plausible |
| 102 | 16 | **second passcode, clear text** | community |

The passcodes are why this project never decodes, logs or serves the whole
device info frame, and why `tools/dump_frames.py` leaves type `03` frames out
unless asked. Do not paste such a frame into a bug report.

## What is not here

- Writing settings (the write commands exist in the protocol; this project is read-only on purpose).
- The 24-cell frame layout of older hardware.
- Temperature sensors 3–5 and the other fields of newer hardware.
- The meaning of the individual alarm bits.

## Sources

The frame layout was first documented by the community, most thoroughly in
[syssi/esphome-jk-bms](https://github.com/syssi/esphome-jk-bms). The offsets in
this project come from the program this one grew out of, whose author compared
the settings frame with a dump from his own device, and were checked again on
captured frames as described at the top.
