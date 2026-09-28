"""
Runs one effect at a time on a background thread.

The runner pulls frames from an effect generator and pushes each color to the
mouse. If the mouse disappears (dongle asleep, cable pulled), it waits and
retries instead of dying, so effects resume on their own when the mouse wakes.
"""

from __future__ import annotations

import threading
from typing import Callable, Iterator

from . import protocol as p
from .device import R5Mouse
from .effects import EffectContext, Frame, dim

FramesFn = Callable[[EffectContext], Iterator[Frame]]


class EffectRunner:
    RETRY_SECONDS = 1.5

    def __init__(self, mouse: R5Mouse, ctx: EffectContext,
                 profile: Callable[[], int], brightness: Callable[[], int],
                 log: Callable[[str], None] = lambda _msg: None,
                 on_frame: Callable[[p.RGB], None] = lambda _rgb: None):
        self.mouse = mouse
        self.ctx = ctx
        self.profile = profile
        self.brightness = brightness
        self.log = log
        self.on_frame = on_frame   # called with each color after it's sent (live preview)
        self.running_key: str | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, key: str, frames: FramesFn):
        self.stop()
        self._stop = threading.Event()
        self.running_key = key
        self._thread = threading.Thread(target=self._run, args=(key, frames, self._stop),
                                        name=f"effect-{key}", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 1.0):
        self._stop.set()
        if self._thread and self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout)
        self._thread = None
        self.running_key = None

    def _prepare(self, profile: int):
        """Brightness and 'never sleep' once, before the first frame."""
        with self.mouse:
            self.mouse.send(p.lightness(profile, 255, self.mouse.wired))    # brightness is done in the color
            self.mouse.send(p.sleep_time(profile, p.SLEEP_NEVER))

    def _run(self, key: str, frames: FramesFn, stop: threading.Event):
        try:
            self._loop(key, frames(self.ctx), stop)
        except Exception as exc:          # a bug or missing input inside the effect
            self.log(f"Effect {key} stopped: {exc}")
        finally:
            if self._stop is stop:
                self.running_key = None

    def _loop(self, key: str, generator: Iterator[Frame], stop: threading.Event):
        prepared = False
        offline = False
        for rgb, hold in generator:
            if stop.is_set():
                return
            try:
                profile = self.profile()
                if not prepared:
                    self._prepare(profile)
                    prepared = True
                self.mouse.push_color(profile, dim(rgb, self.brightness()))
            except (OSError, ValueError) as exc:   # hidapi raises both
                # Usually the dongle went to sleep or re-enumerated. Back off
                # and retry; brightness is re-sent once it's back.
                if not offline:
                    self.log(f"Effect {key}: mouse unavailable ({exc}); will resume when it's back")
                    offline = True
                self.mouse.reset()
                prepared = False
                if stop.wait(self.RETRY_SECONDS):
                    return
                continue
            self.on_frame(rgb)
            if offline:
                self.log(f"Effect {key}: mouse is back")
                offline = False
            if stop.wait(max(0.0, hold)):
                return
