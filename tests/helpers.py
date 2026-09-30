"""Small things several test files need."""

import threading
import time

from dorsal import firmware as fw
from test_firmware import fake_stock


def wait(cond, seconds=5):
    end = time.time() + seconds
    while time.time() < end and not cond():
        time.sleep(0.01)
    assert cond()


def wait_idle(seconds=20):
    """Until every background job of the controller is over, its finishing step included. Waiting for the busy
    flag isn't enough: it goes down just before the result is published."""
    wait(lambda: not any(t.name.startswith("work-") and t.is_alive() for t in threading.enumerate()), seconds)


def cables(*present):
    """A stand-in for core._cable_check: `present` is [(model, state), ...]. Asked about no mouse in particular it
    gives the best one (a bootloader beats a cable beats a dongle, then table order), asked about one it says
    where that one is."""
    order = {"bootloader": 0, "cable": 1, "dongle": 2}

    def check(model=None):
        found = [(order[state], i, m, state) for i, (m, state) in enumerate(present) if model in (None, m)]
        if not found:
            return "none", None
        _, _, m, state = min(found, key=lambda t: t[:2])
        return state, m
    return check


def settle(controller, seconds=20):
    """Leave nothing of a Controller running behind a test: its colour timers cancelled, its workers finished.
    (A worker that outlives the test calls the real hidapi once the fake is gone, and can crash the interpreter.)"""
    for timer in (controller._live_timer, controller._dpi_timer):
        if timer is not None:
            timer.cancel()
    wait_idle(seconds)


def variant(n=0):
    """A fake stock image that's different from the next number's by one byte, so two versions of a mouse can
    sit side by side in the table of known images."""
    ih = fake_stock()
    ih[ih.minaddr()] = ih[ih.minaddr()] ^ (1 << (n % 8))
    return ih


def register(monkeypatch, *entries):
    """Make (model, version, stock image) triples the only images Dorsal knows. Returns [(stock, patched)]."""
    known, out = [], []
    for model, version, stock in entries:
        patched = fw.apply_patch(stock)
        kw = dict(start=stock.minaddr(), end=stock.maxaddr(), model=model.key)
        known += [fw.KnownImage(f"fake {model.name} firmware v{version} (stock)", fw.image_sha256(stock),
                                patched=False, patch=fw.PATCH_A, **kw),
                  fw.KnownImage(f"fake {model.name} firmware v{version} (patched)", fw.image_sha256(patched),
                                patched=True, **kw)]
        out.append((stock, patched))
    monkeypatch.setattr(fw, "KNOWN_IMAGES", tuple(known))
    return out
