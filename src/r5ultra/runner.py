"""Plays one lighting effect at a time in the background."""

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
        self.on_frame = on_frame
        self.running_key: str | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

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
        with self.mouse:
            self.mouse.send(p.lightness(profile, 255, self.mouse.wired))
            self.mouse.send(p.sleep_time(profile, p.SLEEP_NEVER))

    def _run(self, key: str, frames: FramesFn, stop: threading.Event):
        try:
            self._loop(key, frames(self.ctx), stop)
        except Exception as exc:
            self.log(f"Effect {key} stopped: {exc}")
        finally:
            if self._stop is stop:
                self.running_key = None

    def _loop(self, key: str, generator: Iterator[Frame], stop: threading.Event):
        prepared = False
        offline = False
        held = False
        last = None
        try:
            for rgb, hold in generator:
                if stop.is_set():
                    return
                try:
                    profile = self.profile()
                    color = dim(rgb, self.brightness())
                    if not prepared:
                        self._prepare(profile)
                        if not held:        # keep it open the whole effect, reopening costs ~16 ms a frame
                            self.mouse.__enter__()
                            held = True
                        self.mouse.push_color(profile, color, set_mode=True)
                        prepared, last = True, color
                    elif color != last:     # don't resend what the LED already shows
                        self.mouse.push_color(profile, color, set_mode=False)
                        last = color
                except (OSError, ValueError) as exc:   # usually the dongle went to sleep
                    if not offline:
                        self.log(f"Effect {key}: mouse unavailable ({exc}); will resume when it's back")
                        offline = True
                    self.mouse.reset()
                    held = prepared = False
                    if stop.wait(self.RETRY_SECONDS):
                        return
                    continue
                self.on_frame(rgb)
                if offline:
                    self.log(f"Effect {key}: mouse is back")
                    offline = False
                if stop.wait(max(0.0, hold)):
                    return
        finally:
            if held:
                self.mouse.__exit__(None, None, None)
