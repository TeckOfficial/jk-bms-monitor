"""Tests for the optional socket automation, against pretend plugs and a pretend clock.

Run with:  python -m unittest discover -s tests
"""
import asyncio
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from jkbms import demo                                        # noqa: E402
from jkbms.sockets import RETRY_S, SocketController, SocketError  # noqa: E402


class Bench:
    """A controller with two plugs, a settable battery and a settable clock."""

    def __init__(self, **config):
        self.now = 1000.0
        self.soc, self.age = 50.0, 1.0
        self.plugs: dict[str, demo.DemoPlug] = {}
        self.log: list[str] = []
        settings = {"on_soc": 95, "off_soc": 90, "bms_stale_min": 10,
                    "devices": [{"name": "Heater", "ip": "a"}, {"name": "Pump", "ip": "b"}]}
        settings.update(config)
        self.ctl = SocketController(settings, lambda: (self.soc, self.age), connect=demo.demo_connector(self.plugs),
                                    log=self.log.append, clock=lambda: self.now)

    def step(self, soc=None, age=None, wait=30.0):
        if soc is not None:
            self.soc = soc
        if age is not None:
            self.age = age
        self.now += wait
        asyncio.run(self.ctl.step())
        return [self.plugs[ip].is_on if ip in self.plugs else None for ip in ("a", "b")]

    def socket(self, ident):
        return next(d for d in self.ctl.snapshot()["devices"] if d["id"] == ident)


class Automation(unittest.TestCase):
    def test_hysteresis(self):
        b = Bench()
        self.assertEqual(b.step(soc=50), [False, False])
        self.assertEqual(b.step(soc=94), [False, False], "below the on threshold nothing happens")
        self.assertEqual(b.step(soc=95), [True, True])
        self.assertEqual(b.socket("s1")["reason"], "soc")
        self.assertEqual(b.step(soc=91), [True, True], "between the thresholds the state is kept")
        self.assertEqual(b.step(soc=90), [False, False])
        self.assertEqual(b.step(soc=92), [False, False], "and it does not come back until on_soc")

    def test_per_socket_thresholds(self):
        b = Bench(devices=[{"name": "Heater", "ip": "a"}, {"name": "Pump", "ip": "b", "on_soc": 60, "off_soc": 40}])
        self.assertEqual(b.step(soc=70), [False, True])
        self.assertEqual(b.step(soc=96), [True, True])
        self.assertEqual(b.step(soc=85), [False, True])
        self.assertEqual(b.step(soc=40), [False, False])

    def test_nothing_happens_without_a_state_of_charge(self):
        b = Bench()
        b.soc = None
        self.assertEqual(b.step(), [False, False])

    def test_bad_thresholds_are_refused(self):
        with self.assertRaises(ValueError):
            Bench(on_soc=80, off_soc=80)

    def test_socket_without_address_is_skipped(self):
        b = Bench(devices=[{"name": "Heater", "ip": ""}, {"name": "Pump", "ip": "b"}])
        self.assertEqual([d["id"] for d in b.ctl.snapshot()["devices"]], ["s2"])


class Failsafe(unittest.TestCase):
    def test_stale_bms_turns_automatic_sockets_off_and_keeps_them_off(self):
        b = Bench()
        self.assertEqual(b.step(soc=97), [True, True])
        self.assertEqual(b.step(age=599), [True, True], "ten minutes are allowed")
        self.assertEqual(b.step(age=601), [False, False])
        self.assertTrue(b.socket("s1")["bms_stale"])
        self.assertEqual(b.step(soc=99, age=900), [False, False], "the old state of charge must not turn it on")
        self.assertEqual(b.step(soc=99, age=2), [True, True], "fresh data: automation continues")

    def test_stale_bms_leaves_manual_sockets_alone(self):
        b = Bench()
        b.step(soc=50)
        asyncio.run(b.ctl.switch("s1", True))
        self.assertEqual(b.step(age=5000), [True, False])

    def test_failsafe_can_be_disabled(self):
        b = Bench(bms_stale_min=0)
        b.step(soc=97)
        self.assertEqual(b.step(age=99999), [True, True])

    def test_before_the_first_bms_data_nothing_is_switched_on(self):
        b = Bench()
        b.soc, b.age = None, None
        self.assertEqual(b.step(), [False, False])


class Manual(unittest.TestCase):
    def test_manual_mode_is_not_touched_by_the_automation(self):
        b = Bench()
        b.step(soc=50)
        state = asyncio.run(b.ctl.switch("s1", True))
        self.assertEqual((state["on"], state["mode"], state["reason"]), (True, "manual", "manual"))
        self.assertEqual(b.step(soc=10), [True, False], "manual socket stays on at a low state of charge")
        self.assertEqual(b.step(soc=99), [True, True])
        asyncio.run(b.ctl.switch("s2", False))
        self.assertEqual(b.step(soc=99), [True, False], "manual socket stays off at a high state of charge")

    def test_back_to_auto(self):
        b = Bench()
        b.step(soc=50)
        asyncio.run(b.ctl.switch("s1", True))
        self.assertEqual(b.ctl.set_mode("s1", "auto")["mode"], "auto")
        self.assertEqual(b.step(soc=92), [True, False], "between the thresholds the state is kept")
        self.assertEqual(b.step(soc=90), [False, False], "and from here on the rule decides again")

    def test_switch_reconnects_once_after_an_expired_session(self):
        b = Bench()
        b.step(soc=50)
        old = b.plugs["a"]
        old.broken = True                         # the session we hold is dead ...
        b.plugs["a"] = demo.DemoPlug()            # ... but a fresh login works
        state = asyncio.run(b.ctl.switch("s1", True))
        self.assertTrue(state["on"])
        self.assertTrue(b.plugs["a"].is_on)

    def test_errors_are_reported(self):
        b = Bench()
        with self.assertRaises(SocketError):
            asyncio.run(b.ctl.switch("nope", True))
        with self.assertRaises(SocketError):
            b.ctl.set_mode("s1", "sometimes")
        b.step(soc=50)
        b.plugs["a"].broken = True
        with self.assertRaises(SocketError):
            asyncio.run(b.ctl.switch("s1", True))


class Unreachable(unittest.TestCase):
    def test_dead_plug_is_retried_with_growing_pauses_and_does_not_block_the_other(self):
        b = Bench()
        dead = b.plugs["a"] = demo.DemoPlug()
        dead.broken = True
        self.assertEqual(b.step(soc=97), [False, True], "the reachable socket still works")
        self.assertFalse(b.socket("s1")["connected"])
        attempts = sum("unreachable" in line for line in b.log)
        self.assertEqual(attempts, 1)
        b.step(wait=RETRY_S[0] - 5)               # too early: no new attempt
        dead.broken = False
        self.assertFalse(b.socket("s1")["connected"])
        b.step(wait=10)                           # pause is over: connects and follows the rule
        self.assertTrue(b.socket("s1")["connected"])
        self.assertTrue(dead.is_on)
        self.assertEqual(sum("unreachable" in line for line in b.log), 1, "the failure is logged once")

    def test_plug_switched_by_hand_is_noticed(self):
        b = Bench()
        b.step(soc=97)
        b.plugs["a"].is_on = False                # someone pressed the button on the plug
        self.assertEqual(b.step(soc=93), [False, True], "state is read back; no switching between thresholds")
        self.assertFalse(b.socket("s1")["on"])


if __name__ == "__main__":
    unittest.main()
