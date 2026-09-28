import threading
import time

from r5ultra import protocol as p
from r5ultra.effects import EffectContext
from r5ultra.runner import EffectRunner


class FakeMouse:
    """Records what would have gone over USB. Can simulate the dongle
    disappearing for the first `fail_first` frames."""

    wired = False

    def __init__(self, fail_first=0):
        self.frames, self.sent, self.resets = [], [], 0
        self.fail_first = fail_first
        self.lock = threading.Lock()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def send(self, payload, read_back=True):
        self.sent.append(payload)
        return b""

    def push_color(self, profile, rgb, set_mode=True):
        with self.lock:
            self.modes = getattr(self, "modes", []) + [set_mode]
            if self.fail_first > 0:
                self.fail_first -= 1
                raise OSError("device disconnected")
            self.frames.append((profile, rgb))

    def reset(self):
        self.resets += 1


def colors(ctx):
    n = 0
    while True:
        yield (n % 256, 0, 0), 0.001
        n += 1


def wait_until(condition, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if condition():
            return True
        time.sleep(0.005)
    return False


def test_runner_pushes_frames_and_stops():
    mouse = FakeMouse()
    runner = EffectRunner(mouse, EffectContext(), profile=lambda: 2, brightness=lambda: 150)
    runner.start("test", colors)
    assert wait_until(lambda: len(mouse.frames) > 20)
    runner.stop()
    count = len(mouse.frames)
    time.sleep(0.05)
    assert len(mouse.frames) == count                 # really stopped
    assert runner.running_key is None
    assert mouse.frames[0] == (2, (0, 0, 0))
    # brightness is done in the color now, so the firmware setting stays at max
    assert mouse.sent[:2] == [p.lightness(2, 255), p.sleep_time(2, p.SLEEP_NEVER)]


def test_runner_survives_the_mouse_disappearing():
    logs = []
    mouse = FakeMouse(fail_first=2)
    # full brightness, so every frame is a new color (repeats aren't resent)
    runner = EffectRunner(mouse, EffectContext(), profile=lambda: 1, brightness=lambda: 255, log=logs.append)
    runner.RETRY_SECONDS = 0.01
    runner.start("test", colors)
    assert wait_until(lambda: len(mouse.frames) > 5)
    runner.stop()
    assert mouse.resets == 2
    assert sum("unavailable" in m for m in logs) == 1   # logged once, not every retry
    assert any("back" in m for m in logs)


def test_runner_logs_effects_that_crash():
    logs = []

    def broken(ctx):
        yield (1, 1, 1), 0.001
        raise ValueError("oops")

    runner = EffectRunner(FakeMouse(), EffectContext(), profile=lambda: 1, brightness=lambda: 1, log=logs.append)
    runner.start("broken", broken)
    assert wait_until(lambda: any("oops" in m for m in logs))
    assert wait_until(lambda: runner.running_key is None)


def test_starting_a_new_effect_replaces_the_old_one():
    mouse = FakeMouse()
    runner = EffectRunner(mouse, EffectContext(), profile=lambda: 1, brightness=lambda: 255)
    runner.start("a", colors)
    runner.start("b", lambda ctx: iter([((9, 9, 9), 0.001)] * 10_000))
    assert runner.running_key == "b"
    assert wait_until(lambda: (1, (9, 9, 9)) in mouse.frames)
    runner.stop()
    assert threading.active_count() < 10


def test_runner_sets_the_mode_once_and_skips_repeated_colors():
    mouse = FakeMouse()
    runner = EffectRunner(mouse, EffectContext(), profile=lambda: 1, brightness=lambda: 255)
    frames = [((10, 0, 0), 0.001)] * 5 + [((20, 0, 0), 0.001)] * 5 + [((30, 0, 0), 5)]
    runner.start("steady", lambda ctx: iter(frames))
    assert wait_until(lambda: len(mouse.frames) == 3)
    runner.stop()
    assert [rgb for _p, rgb in mouse.frames] == [(10, 0, 0), (20, 0, 0), (30, 0, 0)]
    assert mouse.modes == [True, False, False]
