"""Tests for frame assembly and decoding. Run with:  python -m unittest discover -s tests

No Bluetooth and no extra packages needed.
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from jkbms import demo, protocol                # noqa: E402

FRAMES = pathlib.Path(__file__).resolve().parent / "frames"


def chunks(frame: bytes, size: int):
    return [frame[i:i + size] for i in range(0, len(frame), size)]


class Commands(unittest.TestCase):
    def test_known_packets(self):
        # the two requests as they appear in every capture of the vendor app
        self.assertEqual(protocol.build_command(protocol.CMD_DEVICE_INFO).hex(),
                         "aa5590eb97" + "00" * 14 + "11")
        self.assertEqual(protocol.build_command(protocol.CMD_CELL_INFO).hex(),
                         "aa5590eb96" + "00" * 14 + "10")


class Assembler(unittest.TestCase):
    def setUp(self):
        self.frame = demo.encode_cell_data([3.30] * 8, 5.0, 50)

    def test_any_chunk_size(self):
        for size in (20, 128, 172, 244, 300):
            assembler = protocol.FrameAssembler()
            got = [f for chunk in chunks(self.frame, size) for f in assembler.feed(chunk)]
            self.assertEqual(got, [self.frame], f"chunk size {size}")

    def test_bad_checksum_is_dropped_and_counted(self):
        broken = bytearray(self.frame)
        broken[100] ^= 0xFF
        assembler = protocol.FrameAssembler()
        got = [f for chunk in chunks(bytes(broken), 128) for f in assembler.feed(chunk)]
        self.assertEqual(got, [])
        self.assertEqual(assembler.checksum_errors, 1)

    def test_keepalive_and_trailing_bytes_are_ignored(self):
        assembler = protocol.FrameAssembler()
        self.assertEqual(assembler.feed(protocol.KEEPALIVE), [])
        padded = self.frame + bytes(20)             # some firmwares pad frames to 320 bytes
        got = [f for chunk in chunks(padded, 128) for f in assembler.feed(chunk)]
        self.assertEqual(got, [self.frame])
        got = [f for chunk in chunks(self.frame, 128) for f in assembler.feed(chunk)]
        self.assertEqual(got, [self.frame], "the next frame must still be recognised")

    def test_new_header_restarts_a_torn_frame(self):
        assembler = protocol.FrameAssembler()
        assembler.feed(self.frame[:128])            # connection hiccup: the rest never arrives
        got = [f for chunk in chunks(self.frame, 128) for f in assembler.feed(chunk)]
        self.assertEqual(got, [self.frame])
        self.assertEqual(assembler.checksum_errors, 0)

    def test_header_in_the_middle_of_a_notification(self):
        # seen on real hardware: the module glues its "AT" keep-alive in front of a frame
        assembler = protocol.FrameAssembler()
        stream = protocol.KEEPALIVE + self.frame
        got = [f for chunk in chunks(stream, 128) for f in assembler.feed(chunk)]
        self.assertEqual(got, [self.frame])
        self.assertEqual(assembler.checksum_errors, 0)

    def test_header_split_between_notifications(self):
        assembler = protocol.FrameAssembler()
        stream = bytes(7) + self.frame
        got = assembler.feed(stream[:9]) + assembler.feed(stream[9:150]) + assembler.feed(stream[150:])
        self.assertEqual(got, [self.frame])

    def test_resync_after_a_torn_frame_without_a_clean_start(self):
        assembler = protocol.FrameAssembler()
        got = assembler.feed(self.frame[:100] + self.frame + self.frame)
        self.assertEqual(got, [self.frame, self.frame])
        self.assertEqual(assembler.checksum_errors, 1)


class RoundTrip(unittest.TestCase):
    def test_cell_data(self):
        cells = [3.301, 3.305, 3.298, 3.312, 3.300, 3.299, 3.307, 3.303]
        frame = demo.encode_cell_data(cells, -12.345, 67, mos_temp=31.5, temp1=-4.2, temp2=18.0,
                                      remain_ah=187.6, nominal_ah=280.0, cycles=42, cycled_ah=11760.5,
                                      soh=98, runtime_s=1234567, balance_action=2, balance_current=-0.6,
                                      mos_charge=True, mos_discharge=False)
        kind, data = protocol.decode(frame)
        s = data["summary"]
        self.assertEqual(kind, "cell_data")
        self.assertEqual(data["cells"], cells)
        self.assertEqual(len(data["resistances"]), 8)
        self.assertAlmostEqual(s["total_voltage"], sum(cells), places=3)
        self.assertEqual(s["current"], -12.345)
        self.assertLess(s["power"], 0, "power takes the sign of the current")
        self.assertAlmostEqual(s["power"], sum(cells) * -12.345, places=2)
        self.assertEqual((s["soc"], s["soh"], s["cycles"], s["runtime_s"]), (67, 98, 42, 1234567))
        self.assertEqual((s["mos_temp"], s["temp1"], s["temp2"]), (31.5, -4.2, 18.0))
        self.assertEqual((s["max_cell_idx"], s["min_cell_idx"]), (3, 2))
        self.assertEqual(s["delta_mv"], 14)
        self.assertEqual((s["remain_ah"], s["nominal_ah"], s["cycled_ah"]), (187.6, 280.0, 11760.5))
        self.assertEqual((s["balance_action"], s["balance_current"]), (2, -0.6))
        self.assertEqual((s["mos_charge"], s["mos_discharge"]), (True, False))
        self.assertEqual((s["alarm"], s["alarms_hex"]), (False, "0x00000000"))

    def test_fewer_and_more_cells(self):
        for count in (4, 16, 24):
            frame = demo.encode_cell_data([3.2 + i / 1000 for i in range(count)], 1.0, 50)
            self.assertEqual(len(protocol.decode(frame)[1]["cells"]), count)

    def test_settings(self):
        kind, data = protocol.decode(demo.encode_settings(demo.DEMO_SETTINGS))
        self.assertEqual(kind, "settings")
        self.assertEqual(data, demo.DEMO_SETTINGS)

    def test_device_info(self):
        kind, data = protocol.decode(demo.encode_device_info(demo.DEMO_DEVICE))
        self.assertEqual(kind, "device_info")
        self.assertEqual(data, demo.DEMO_DEVICE)

    def test_unknown_or_short_frames(self):
        self.assertEqual(protocol.decode(b"\x55\xaa\xeb\x90\x02"), (None, {}))
        frame = bytearray(demo.encode_cell_data([3.3] * 8, 0, 50))
        frame[4] = 0x7F
        self.assertEqual(protocol.decode(bytes(frame)), (None, {}))


class RealFrames(unittest.TestCase):
    """Frames captured from a JK-B2A20S20P (hardware 19, firmware 19.10), see tests/frames/README.md."""

    def load(self, name):
        path = FRAMES / name
        if not path.exists():
            self.skipTest(f"{name} not present")
        return bytes.fromhex(path.read_text().split()[-1])

    def test_cell_data(self):
        frame = self.load("cell_data.hex")
        assembler = protocol.FrameAssembler()
        self.assertEqual([f for c in chunks(frame, 128) for f in assembler.feed(c)], [frame], "checksum")
        kind, data = protocol.decode(frame)
        s = data["summary"]
        self.assertEqual(kind, "cell_data")
        self.assertEqual(len(data["cells"]), 8)
        self.assertTrue(all(2.5 < v < 3.7 for v in data["cells"]), data["cells"])
        self.assertAlmostEqual(s["total_voltage"], s["sum_cells"], delta=0.05)
        self.assertAlmostEqual(abs(s["power"]), abs(s["total_voltage"] * s["current"]), delta=1.0)
        self.assertTrue(0 <= s["soc"] <= 100 and s["soh"] <= 100)
        self.assertEqual(s["nominal_ah"], 360.0)
        # highest / lowest cell are indexes from 0: in this frame cell 1 is a highest and cell 2 a lowest one
        self.assertEqual((s["max_cell_idx"], s["min_cell_idx"]), (0, 1))
        self.assertEqual(data["cells"][0], max(data["cells"]))
        self.assertEqual(data["cells"][1], min(data["cells"]))
        self.assertAlmostEqual(s["remain_ah"], s["nominal_ah"] * s["soc"] / 100, delta=4)
        self.assertTrue(-20 < s["temp1"] < 60 and -20 < s["temp2"] < 60 and -20 < s["mos_temp"] < 90)

    def test_settings(self):
        kind, data = protocol.decode(self.load("settings.hex"))
        self.assertEqual(kind, "settings")
        self.assertEqual(data["cell_count"], 8)
        self.assertEqual(data["capacity_ah"], 360.0)
        self.assertEqual((data["cell_uvp"], data["cell_ovp"]), (2.6, 3.6))
        self.assertEqual((data["balance_start_v"], data["balance_delta_mv"]), (3.4, 10))
        self.assertEqual((data["max_charge_a"], data["max_discharge_a"]), (150.0, 200.0))


class Demo(unittest.TestCase):
    def test_a_simulated_day_stays_plausible(self):
        battery = demo.DemoBattery()
        points = battery.history(24)
        self.assertEqual(len(points), 24 * 60)
        self.assertTrue(all(0 <= p["soc"] <= 100 for p in points))
        self.assertTrue(all(20 < p["voltage"] < 29 for p in points))
        self.assertGreater(max(p["power"] for p in points), 200, "the sun should charge at some point")
        self.assertLess(min(p["power"] for p in points), -100, "the house should draw at some point")


if __name__ == "__main__":
    unittest.main()
