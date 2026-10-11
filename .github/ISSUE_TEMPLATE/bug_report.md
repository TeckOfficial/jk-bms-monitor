---
name: Wrong or missing value / it does not connect
about: Something the dashboard shows is wrong, or the BMS cannot be read
labels: bug
---

**BMS**

- Model (as printed on the unit, e.g. JK-B2A20S20P):
- Hardware / firmware version (vendor app → About):
- Number of cells and chemistry:

**Computer**

- Device and system (e.g. Raspberry Pi Zero 2 W, Raspberry Pi OS 13):
- Python version (`python3 --version`):

**What happens**

<!-- What do you see, and what does the vendor app show at the same moment? -->

**Log**

<!-- journalctl -u jk-bms-monitor -n 50   (or what the program printed) -->

```
```

**Frames** (for wrong values)

<!--
Stop the monitor, then run:
    venv/bin/python tools/dump_frames.py --address <address> --out frames.txt
and attach frames.txt.

Do NOT use --include-device-info here: those frames contain your serial
number and the Bluetooth passcodes in clear text.
-->
