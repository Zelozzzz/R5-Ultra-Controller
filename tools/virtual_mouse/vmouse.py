"""A fake nRF52840 that boots real mouse firmware.

The CPU is Unicorn running the actual firmware from the reset vector. Around it
are just enough fake peripherals to keep the firmware happy: clocks and flash
always report ready, timers fire at whatever rate the firmware sets them to,
and the interrupt controller behaves like the real one. Buttons, the mode
switch and the USB cable are plain inputs you can flip.

It can't do radio, USB data or the sensor. Anything that needs those has to be
faked from the outside (see dorsal_check.py).

Flash acts like real flash: erasing a page fills it with FF, and every erase is
counted per page so you can see wear. A write that tries to turn a 0 bit back
into 1 without an erase first (which real flash can't do) is counted too.
Deep sleep (System OFF) stops the CPU until a button with wake-up turned on
gets pressed or the cable goes in, then the chip boots again like the real one.
The watchdog resets the chip if the firmware stops feeding it.
"""
from __future__ import annotations

import copy
import re
import struct
from collections import Counter

from intelhex import IntelHex
from unicorn import (UC_ARCH_ARM, UC_HOOK_CODE, UC_HOOK_INSN_INVALID, UC_HOOK_INTR, UC_HOOK_MEM_WRITE, UC_MODE_MCLASS,
                     UC_MODE_THUMB, Uc, UcError)
from unicorn.arm_const import (UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                               UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
                               UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11, UC_ARM_REG_R12,
                               UC_ARM_REG_SP, UC_ARM_REG_XPSR, UC_ARM_REG_PRIMASK, UC_ARM_REG_BASEPRI,
                               UC_ARM_REG_FAULTMASK, UC_ARM_REG_CONTROL, UC_ARM_REG_MSP, UC_ARM_REG_PSP)

PWM = {0x4001C000: ("PWM0", 28), 0x40021000: ("PWM1", 33), 0x40022000: ("PWM2", 34), 0x4002D000: ("PWM3", 45)}
TIMERS = {8: 0x40008000, 9: 0x40009000, 10: 0x4000A000, 26: 0x4001A000, 27: 0x4001B000}
RTCS = (11, 17, 36)
WATCHDOG = 0x40010000
WDT_FEED = 0x6E524635
NVMC_CONFIG, NVMC_ERASEPAGE, NVMC_ERASEALL, NVMC_ERASEPARTIAL = 0x4001E504, 0x4001E508, 0x4001E50C, 0x4001E518
SYSTEMOFF = 0x40000500
CLOCK_TASKS = {0x40000000: ("hf", True), 0x40000004: ("hf", False), 0x40000008: ("lf", True), 0x4000000C: ("lf", False)}
POWER_CLOCK = 0x40000000
# the event each CLOCK task really makes (the stop tasks make none): HFCLKSTARTED, LFCLKSTARTED,
# DONE (calibration), CTSTARTED, CTSTOPPED. calibration timeout (CTTO) never fires here
CLOCK_EVENTS = {0x000: 0x100, 0x008: 0x104, 0x010: 0x10C, 0x014: 0x128, 0x018: 0x12C}
USBDETECTED, USBREMOVED, USBPWRRDY = 0x11C, 0x120, 0x124
SPIM3 = 0x4002F000                  # the sensor's SPI port
SAADC = 0x40007000                  # the ADC these mice read the battery with (AIN7, 12 bit)
GPIOTE = 0x40006000
FLASH_SIZE, PAGE = 0x100000, 0x1000
RET = 0x000FFF00                    # fake return address when we call an interrupt handler
SAVED = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5,
         UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
         UC_ARM_REG_R12, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_XPSR]
# the rest of the CPU state, only needed when saving (CONTROL first, then the stack pointers)
SYSTEM = [UC_ARM_REG_CONTROL, UC_ARM_REG_PRIMASK, UC_ARM_REG_BASEPRI, UC_ARM_REG_FAULTMASK, UC_ARM_REG_MSP, UC_ARM_REG_PSP]
DELAY_LOOP = bytes.fromhex("0338fdd87047")    # subs r0,#3 / bhi . / bx lr  (nrf_delay_us)


class PixartSensor:
    """The PAW3950 motion sensor, on the chip's fast SPI port (SPIM3).

    Just enough of it for the firmware to find it and set it up: register banks
    (register 0x7F picks the bank), the product id, the "power-up done" flag the
    firmware waits for, and the motion burst it reads every poll. move() makes the
    next motion read report that much movement, like sliding the mouse.
    """
    PRODUCT_ID = 0x53          # the R5/M5 firmware also takes 0x51 (a PAW3395), 0x53 is the 3950
    BURST = 0x16

    def __init__(self):
        self.regs: dict[tuple[int, int], int] = {}
        self.bank = 0
        self.addr = 0
        self.dx = self.dy = 0
        self.motion_reads = 0

    def move(self, dx: int, dy: int):
        self.dx += dx
        self.dy += dy

    def transfer(self, tx: bytes, n_rx: int) -> bytes:
        if tx and tx[0] & 0x80:                          # writes come as (address | 0x80, value) pairs
            for i in range(0, len(tx) - 1, 2):
                a, v = tx[i] & 0x7F, tx[i + 1]
                if a == 0x7F:
                    self.bank = v
                else:
                    self.regs[(self.bank, a)] = v
            return bytes(n_rx)
        if tx:
            self.addr = tx[0] & 0x7F
        if not n_rx:
            return b""
        data = self._read(self.addr, n_rx)
        return (bytes(len(tx)) + data)[:n_rx] if tx else data   # full duplex: nothing useful during the address

    def _read(self, addr, n):
        if self.bank == 0 and addr == self.BURST:
            self.motion_reads += 1
            dx, dy = max(-32768, min(32767, self.dx)), max(-32768, min(32767, self.dy))
            self.dx, self.dy = self.dx - dx, self.dy - dy
            out = bytes([0x80 if dx or dy else 0, 0]) + dx.to_bytes(2, "little", signed=True)                 + dy.to_bytes(2, "little", signed=True)
            return (out + bytes(12))[:n]
        out = []
        for i in range(n):
            a = addr + i
            if self.bank == 0 and a == 0x00:
                out.append(self.PRODUCT_ID)
            elif self.bank == 0 and a == 0x6C:
                out.append(0x80)                         # power-up done
            else:
                out.append(self.regs.get((self.bank, a), 0))
        return bytes(out)


class VirtualMouse:
    # PWM units that keep real time: a started sequence takes as long as its settings say, and "loops
    # done" only happens then. This matters: the LED firmware copies the wanted color into the PWM's
    # buffer when a loop finishes, so a loop that lasts minutes freezes the LED (patch D in
    # docs/FIRMWARE.md). False = the old fake, every PWM reports a finished sequence every millisecond
    real_time_pwm = True

    # Unicorn itself falls over after a few minutes of these millions of tiny runs (an access
    # violation deep inside it), so the CPU engine gets rebuilt from a snapshot this often.
    # the firmware can't tell, everything it can see is carried over
    ENGINE_LIFETIME_US = 20e6

    def __init__(self, image: bytes, base: int = 0x27000):
        self.img = image
        self.base = base
        flash = bytearray(b"\xff" * FLASH_SIZE)          # erased flash, so no saved settings
        flash[base:base + len(image)] = image
        uicr = bytearray(b"\xff" * 0x2000)                # FICR + UICR
        uicr[0x10:0x18] = struct.pack("<II", PAGE, FLASH_SIZE // PAGE)   # page size, page count (Nordic's flash storage needs these)
        uicr[0x100:0x104] = struct.pack("<I", 0x52840)
        self._new_engine(bytes(flash), bytes(uicr))
        self.engines = 1

        self.pins_in = {"P0": 0xFFFFFFFF, "P1": 0xFFFFFFFF}   # everything high = nothing pressed
        self.usb_power = False
        self.hints_skipped = 0
        self.fault_resets = False         # True: a crash restarts the chip instead of stopping the test
        self.faults: list[tuple[float, str]] = []
        self.sensor = PixartSensor()
        self.every_ms: list = []          # things the outside world does every millisecond (a receiver, say)
        self.battery_reading = 2300       # raw ADC value on the battery input. 2300 = 76%, see set_battery()
        self.pwm_pins: dict[str, list[int]] = {}
        self.bluetooth_calls = 0
        self.sd_events: list[int] = []
        self.reboots = 0
        self.time_us = 0.0
        # things the checks look at
        self.erases: Counter = Counter()          # flash page -> times erased
        self.erase_log: list[tuple[float, int]] = []
        self.bad_flash_writes: list[tuple[int, int]] = []
        self.sleeps = 0                           # times the firmware switched the chip off
        self.wakes = 0
        self.watchdog_resets = 0
        self.reset_log: list[tuple[float, str]] = []   # (time, why) for every reboot
        self.off = False
        self._reset_chip()

    def _new_engine(self, flash: bytes, uicr: bytes):
        uc = self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        uc.mem_map(0, FLASH_SIZE)
        uc.mem_write(0, flash)
        uc.mem_map(0x10000000, 0x2000)
        uc.mem_write(0x10000000, uicr)
        uc.mem_map(0x20000000, 0x40000)                  # 256 KB RAM
        uc.mem_map(0xE0000000, 0xE000)
        uc.mmio_map(0xE000E000, 0x1000, self._scs_read, None, self._scs_write, None)
        uc.mem_map(0xE000F000, 0xF1000)
        uc.mmio_map(0x40000000, 0x100000, self._read, 0x40000000, self._write, 0x40000000)
        uc.mmio_map(0x50000000, 0x1000, self._read, 0x50000000, self._write, 0x50000000)
        uc.hook_add(UC_HOOK_INTR, self._svc)
        uc.hook_add(UC_HOOK_MEM_WRITE, self._flash_write, begin=0, end=FLASH_SIZE - 1)
        uc.hook_add(UC_HOOK_INSN_INVALID, self._hint)
        # busy-wait delays return right away instead of burning millions of instructions
        for m in re.finditer(re.escape(DELAY_LOOP), self.img):
            at = self.base + m.start()
            uc.hook_add(UC_HOOK_CODE, self._skip_delay, begin=at, end=at)
        self._engine_used = 0.0                  # mouse time this engine has run

    def renew_engine(self):
        state = self.save()
        self._new_engine(state["flash"], state["uicr"])
        self.load(state, keep_counts=True)
        self.engines += 1

    @classmethod
    def from_hex(cls, path):
        ih = IntelHex(str(path))
        return cls(ih.tobinstr(start=ih.minaddr(), end=ih.maxaddr()), ih.minaddr())

    def _reset_chip(self):
        self.uc.mem_write(0x20000000, bytes(0x40000))
        self.regs: dict[int, int] = {}
        self.scs: dict[int, int] = {}
        self.nvic_on = 0
        self.nvic_pending = 0
        self.pending: set[int] = set()
        self._due: dict[int, float] = {}
        self._last_ms = self.time_us
        self.wdt: dict | None = None              # {"timeout": us, "fed": time} once started
        self.sd_events = []
        self.clocks = {"hf": True, "lf": True}
        self.pwm = {page: dict(playing=False, end=0.0, events=set()) for page in PWM} if self.real_time_pwm else {}
        self.off = False
        self._detect = False
        sp, pc = struct.unpack("<II", self.img[:8])
        self.uc.reg_write(UC_ARM_REG_SP, sp)
        self.pc = pc

    def power_cycle(self):
        """Switch the mouse off and on. Flash (saved settings) survives, RAM doesn't.
        A brand new chip writes its default settings on the first boot, so boot and
        power-cycle once to get a mouse that behaves like one that's been used before."""
        self.sensor = PixartSensor()              # the sensor loses power too
        self._reboot("power")

    def _reboot(self, why):
        self.reboots += 1
        self.reset_log.append((self.time_us, why))
        self._reset_chip()

    # inputs

    def set_pin(self, port, pin, high):
        was = self.pins_in[port] >> pin & 1
        if high:
            self.pins_in[port] |= 1 << pin
        else:
            self.pins_in[port] &= ~(1 << pin)
        if self.off and self._senses(port, pin, high):
            self._wake()
        if was != bool(high) and not self.off:
            self._pin_edge(port, pin, bool(high))
        self._port_detect()

    def plug_usb(self, on: bool):
        self.usb_power = on
        if on and self.off:                       # the cable going in wakes the nRF52840 from System OFF
            self._wake()
        elif not self.off:
            for ev in ((USBDETECTED, USBPWRRDY) if on else (USBREMOVED,)):
                self._clock_event(ev)

    # ADC reading -> the % the firmware reports. measured, same on the R5, M5 and R6
    BATTERY_CURVE = ((1800, 0), (2000, 30), (2200, 61), (2300, 76), (2400, 92), (2500, 100))

    def set_battery(self, percent: float):
        """Put the battery at about this charge level."""
        pts = self.BATTERY_CURVE
        for (r0, p0), (r1, p1) in zip(pts, pts[1:]):
            if percent <= p1:
                self.battery_reading = round(r0 + (r1 - r0) * max(0, percent - p0) / (p1 - p0))
                return
        self.battery_reading = pts[-1][0]

    def _senses(self, port, pin, high):
        cnf = self.regs.get(0x50000000 + (0x700 if port == "P0" else 0xA00) + 4 * pin, 0)
        sense = (cnf >> 16) & 3
        return (sense == 2 and high) or (sense == 3 and not high)

    def _pin_edge(self, port, pin, high):
        """GPIOTE channels in event mode fire on an edge of their pin (the Delux M800 Ultra's
        buttons work like this). The Attack Shark mice poll their buttons instead."""
        number = pin + (32 if port == "P1" else 0)
        for ch in range(8):
            cnf = self.regs.get(GPIOTE + 0x510 + 4 * ch, 0)
            polarity = (cnf >> 16) & 3                      # 1 low to high, 2 high to low, 3 either
            if cnf & 3 == 1 and (cnf >> 8) & 0x3F == number and polarity & (1 if high else 2):
                self._raise_events(GPIOTE, 0x100 + 4 * ch, 0x104 + 4 * ch)
                self.pending.add(6)

    def _port_detect(self):
        """DETECT: any pin whose level matches its sense setting. Going from none to some
        raises GPIOTE's PORT event."""
        detect = self._detect_now()
        if detect and not self._detect and not self.off:
            self._raise_events(GPIOTE, 0x17C, 0x180)
            self.pending.add(6)
        self._detect = detect

    def _detect_now(self):
        return any(self._senses(port, pin, self.pins_in[port] >> pin & 1)
                   for port in ("P0", "P1") for pin in range(32))

    def _wake(self):
        self.wakes += 1
        self._reboot("wake")

    # flash

    def _flash_write(self, uc, access, addr, size, value, user):
        old = int.from_bytes(uc.mem_read(addr, size), "little")
        mask = (1 << (8 * size)) - 1
        # real flash only turns 1s into 0s, and only while writing is switched on
        if self.regs.get(NVMC_CONFIG, 0) & 3 != 1 or (value & mask) & ~old:
            self.bad_flash_writes.append((addr, value & mask))

    def _erase(self, start, length):
        self.uc.mem_write(start, b"\xff" * length)
        for page in range(start, start + length, PAGE):
            self.erases[page] += 1
            self.erase_log.append((self.time_us, page))

    # interrupt controller (NVIC) and system control block

    def _scs_read(self, uc, off, size, user):
        if 0x100 <= off < 0x108 or 0x180 <= off < 0x188:
            return (self.nvic_on >> (32 * ((off & 0x7F) // 4))) & 0xFFFFFFFF
        if 0x200 <= off < 0x208 or 0x280 <= off < 0x288:
            return (self.nvic_pending >> (32 * ((off & 0x7F) // 4))) & 0xFFFFFFFF
        return self.scs.get(off, 0)

    def _scs_write(self, uc, off, size, value, user):
        shift = 32 * ((off & 0x7F) // 4)
        if 0x100 <= off < 0x108:
            self.nvic_on |= value << shift
        elif 0x180 <= off < 0x188:
            self.nvic_on &= ~(value << shift)
        elif 0x200 <= off < 0x208:
            self.nvic_pending |= value << shift
        elif 0x280 <= off < 0x288:
            self.nvic_pending &= ~(value << shift)
        elif off == 0xF00:
            self.nvic_pending |= 1 << (value & 0x1FF)
        else:
            self.scs[off] = value

    # peripherals

    def _read(self, uc, off, size, base):
        addr = base + off
        page, reg = addr & ~0xFFF, addr & 0xFFF
        if page in self.pwm and 0x100 <= reg < 0x200:     # a real-time PWM's events: only what has happened
            return int(reg in self.pwm[page]["events"])
        if page == 0x50000000:
            # P0's registers start at 0x50000500, P1's at 0x50000800
            port, reg = ("P1", reg - 0x300) if reg >= 0x800 else ("P0", reg)
            return self.pins_in[port] if reg == 0x510 else self.regs.get(addr, 0)
        if addr == 0x4000040C:                            # HFCLKSTAT: crystal running, or stopped
            return 0x10001 if self.clocks["hf"] else 0
        if addr == 0x40000418:                            # LFCLKSTAT
            return 0x10001 if self.clocks["lf"] else 0
        if addr == 0x40000438:                            # USB power detected
            return 0b11 if self.usb_power else 0
        if addr in (0x4001E400, 0x4001E408):              # flash controller ready
            return 1
        if page == POWER_CLOCK and 0x100 <= reg < 0x200:  # POWER/CLOCK events only when they really happen
            return self.regs.get(addr, 0)
        if 0x100 <= reg < 0x200:                          # events count as "happened" until cleared
            return self.regs.get(addr, 1)
        return self.regs.get(addr, 0)

    def _write(self, uc, off, size, value, base):
        addr = base + off
        page, reg = addr & ~0xFFF, addr & 0xFFF
        if page < 0x50000000 and reg in (0x300, 0x304, 0x308):
            # INTEN / INTENSET / INTENCLR are one register: SET adds bits, CLR takes them away.
            # the M800 Ultra turns its button interrupts on one at a time
            inten = self.regs.get(page + 0x300, 0)
            old = self.regs.get(page + 0x300, 0)
            inten = value if reg == 0x300 else inten | value if reg == 0x304 else inten & ~value
            for r in (0x300, 0x304, 0x308):
                self.regs[page + r] = inten
            if page == POWER_CLOCK and any(inten & ~old >> b & 1 and self.regs.get(page + 0x100 + 4 * b)
                                           for b in range(32)):
                self.pending.add(0)                       # turning an interrupt on for an event that already happened
            return
        if page in self.pwm and 0x100 <= reg < 0x200:     # the firmware clears a PWM event by writing 0
            self.pwm[page]["events"].add(reg) if value else self.pwm[page]["events"].discard(reg)
            return
        self.regs[addr] = value
        if page == 0x50000000 and (0x700 <= reg < 0x780 or 0xA00 <= reg < 0xA80):
            self._port_detect()                            # a pin's sense setting changed
        if addr in (NVMC_ERASEPAGE, NVMC_ERASEPARTIAL) and value < FLASH_SIZE:
            self._erase(value & ~(PAGE - 1), PAGE)
        elif addr == NVMC_ERASEALL and value & 1:
            self._erase(0, FLASH_SIZE)
        elif addr in (SAADC, SAADC + 4) and value:          # START / SAMPLE: the reading lands in RAM right away
            ptr, count = self.regs.get(SAADC + 0x62C, 0), self.regs.get(SAADC + 0x630, 0)
            if 0x20000000 <= ptr < 0x20040000 and 0 < count <= 64:
                uc.mem_write(ptr, struct.pack("<h", self.battery_reading) * count)
                self.regs[SAADC + 0x634] = count
        elif addr == SPIM3 + 0x10 and value:              # SPI transfer to the sensor
            n_tx, n_rx = self.regs.get(SPIM3 + 0x548, 0), self.regs.get(SPIM3 + 0x538, 0)
            tx = bytes(uc.mem_read(self.regs.get(SPIM3 + 0x544, 0), n_tx)) if n_tx else b""
            rx = self.sensor.transfer(tx, n_rx)
            if n_rx:
                uc.mem_write(self.regs.get(SPIM3 + 0x534, 0), rx)
            self.regs[SPIM3 + 0x53C], self.regs[SPIM3 + 0x54C] = n_rx, n_tx
        elif addr in CLOCK_TASKS and value:                # HFCLKSTART / HFCLKSTOP / LFCLKSTART / LFCLKSTOP
            which, on = CLOCK_TASKS[addr]
            self.clocks[which] = on
        elif addr == SYSTEMOFF and value & 1:
            self.off = True
            self.sleeps += 1
            uc.emu_stop()
        elif page == WATCHDOG:
            if reg == 0 and value:
                crv = self.regs.get(WATCHDOG + 0x504, 0xFFFFFFFF)
                self.wdt = {"timeout": (crv + 1) / 32768 * 1e6, "fed": self.time_us}
            elif 0x600 <= reg < 0x620 and value == WDT_FEED and self.wdt:
                self.wdt["fed"] = self.time_us
        if page in self.pwm and reg == 0x500 and not value & 1:
            self.pwm[page]["playing"] = False                # switched off
        if page == POWER_CLOCK and reg < 0x100 and value:   # a CLOCK task: only its own event
            if reg in CLOCK_EVENTS:
                self._clock_event(CLOCK_EVENTS[reg])
        elif page in self.pwm and reg < 0x100:             # a real-time PWM's task takes as long as it takes
            if value:
                self._pwm_task(page, reg)
        elif page < 0x50000000 and reg < 0x100 and value:  # a task: pretend it finished instantly
            self._raise_events(page, 0x100, 0x200)
            if page != WATCHDOG:
                self.pending.add((page - 0x40000000) >> 12)
        if page in PWM and 0x560 <= reg < 0x570:
            self.pwm_pins.setdefault(PWM[page][0], [0xFFFFFFFF] * 4)[(reg - 0x560) // 4] = value

    def _clock_event(self, ev):
        """A POWER/CLOCK event happens: set it, and interrupt only if the firmware asked for that one.
        The LAMZU and WLMOUSE firmware crash if the calibration timeout reads as happened."""
        self.regs[POWER_CLOCK + ev] = 1
        if self.regs.get(POWER_CLOCK + 0x304, 0) >> ((ev - 0x100) // 4) & 1:
            self.pending.add(0)

    def _raise_events(self, page, lo, hi):
        for ev in range(page + lo, page + hi, 4):
            self.regs.pop(ev, None)

    # real-time PWM. A loop is sequence 0 then sequence 1, LOOP times over. A sequence is
    # COUNTERTOP ticks of 16 MHz / 2^prescaler for every PWM period it uses, and how many periods
    # depends on how many values a period eats (the decoder) and REFRESH / ENDDELAY. LOOPSDONE
    # comes when all of that is over, then the SHORTS say what happens next (stop, or go again).
    # Only the events the firmware asked for (INTEN) interrupt

    def _pwm_raise(self, page, reg):
        self.pwm[page]["events"].add(reg)
        if self.regs.get(page + 0x300, 0) >> ((reg - 0x100) // 4) & 1:
            self.pending.add(PWM[page][1])

    def _pwm_loop_us(self, page):
        r = self.regs
        period = (r.get(page + 0x508, 0x3FF) & 0x7FFF) * (1 << (r.get(page + 0x50C, 0) & 7)) / 16.0
        if r.get(page + 0x504, 0) & 1:
            period *= 2                                        # up-and-down counting
        per_period = {0: 1, 1: 2, 2: 4, 3: 4}[r.get(page + 0x510, 0) & 3]

        def seq(n):
            cnt = r.get(page + 0x524 + 0x20 * n, 0) & 0x7FFF
            return ((cnt / per_period) * (r.get(page + 0x528 + 0x20 * n, 0) + 1) + r.get(page + 0x52C + 0x20 * n, 0)) * period
        loops = r.get(page + 0x514, 0) & 0xFFFF
        return loops * (seq(0) + seq(1)) if loops else seq(0)

    def _pwm_task(self, page, reg):
        st = self.pwm[page]
        if reg == 0x004:                                       # STOP
            st["playing"] = False
            self._pwm_raise(page, 0x104)
        elif reg in (0x008, 0x00C) and self.regs.get(page + 0x500, 0) & 1:   # SEQSTART[n] on an enabled PWM
            st["playing"] = True
            self._pwm_raise(page, 0x108 + (reg - 0x008))
            st["end"] = self.time_us + max(self._pwm_loop_us(page), 1.0)

    def _pwm_tick(self):
        for page, st in self.pwm.items():
            while st["playing"] and self.time_us >= st["end"]:
                for reg in (0x110, 0x114, 0x118, 0x11C):       # both sequences ended, loops done
                    self._pwm_raise(page, reg)
                shorts = self.regs.get(page + 0x200, 0)
                if shorts & 0x10:                              # LOOPSDONE -> STOP
                    st["playing"] = False
                    self._pwm_raise(page, 0x104)
                elif shorts & 0x0C:                            # LOOPSDONE -> SEQSTART again
                    st["end"] += max(self._pwm_loop_us(page), 1.0)
                else:
                    st["playing"] = False

    def _svc(self, uc, intno, user):
        # no Bluetooth stack in here: every call "works" and Bluetooth reports off. the stack's
        # flash calls do happen though, the M800 Ultra saves its settings through them
        if intno != 2:
            raise UcError(21)
        num = uc.mem_read(uc.reg_read(UC_ARM_REG_PC) - 2, 1)[0]
        self.bluetooth_calls += 1
        r0, r1, r2 = (uc.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
        result = 0
        if num == 0x12:                                   # sd_softdevice_is_enabled
            uc.mem_write(r0, bytes(1))
        elif num == 0x29 and r0 + 4 * r2 <= FLASH_SIZE:    # sd_flash_write(dst, src, words)
            old, new = uc.mem_read(r0, 4 * r2), uc.mem_read(r1, 4 * r2)
            uc.mem_write(r0, bytes(a & b for a, b in zip(old, new)))   # flash only turns 1s into 0s
            self._flash_done()
        elif num == 0x28 and r0 < FLASH_SIZE // PAGE:      # sd_flash_page_erase(page)
            self._erase(r0 * PAGE, PAGE)
            self._flash_done()
        elif num == 0x4B:                                 # sd_evt_get(&id): 5 = nothing left
            if self.sd_events:
                uc.mem_write(r0, struct.pack("<I", self.sd_events.pop(0)))
            else:
                result = 5
        uc.reg_write(UC_ARM_REG_R0, result)

    def _flash_done(self):
        self.sd_events.append(2)                          # NRF_EVT_FLASH_OPERATION_SUCCESS
        self.pending.add(22)                              # the stack's event interrupt (SWI2)

    def _hint(self, uc, user):
        # Unicorn rejects WFE and YIELD (it's fine with WFI and SEV). the idle loop uses WFE / SEV / WFE
        # when polling at 8 kHz, WFI below that. Unicorn stops right after the rejected instruction,
        # so treat it like WFI: nothing to do until the next tick
        pc = uc.reg_read(UC_ARM_REG_PC) & ~1
        prev = struct.unpack("<H", bytes(uc.mem_read(pc - 2, 2)))[0]
        if prev in (0xBF10, 0xBF20):
            self.hints_skipped += 1
            uc.emu_stop()
            return True
        return False

    def _skip_delay(self, uc, addr, size, user):
        uc.reg_write(UC_ARM_REG_R0, 0)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    # running

    def _run(self, count):
        try:
            self.uc.emu_start(self.pc, 0xFFFFFFFF, count=count)
        except UcError as e:
            raise RuntimeError(f"firmware crashed ({e}) at {self.uc.reg_read(UC_ARM_REG_PC):#x}") from None
        self.pc = self.uc.reg_read(UC_ARM_REG_PC) | 1
        aircr = self.scs.pop(0xD0C, 0)
        if aircr >> 16 == 0x05FA and aircr & 4:           # firmware asked for a reboot
            self._reboot("firmware")

    def _call(self, fn):
        uc = self.uc
        saved = [uc.reg_read(r) for r in SAVED]
        uc.reg_write(UC_ARM_REG_SP, (saved[13] - 0x80) & ~7)
        uc.reg_write(UC_ARM_REG_LR, RET | 1)
        try:
            uc.emu_start(fn | 1, RET, count=200_000)
        except UcError as e:
            raise RuntimeError(f"interrupt {fn:#x} crashed ({e}) at {uc.reg_read(UC_ARM_REG_PC):#x}") from None
        finally:
            for r, v in zip(SAVED, saved):
                uc.reg_write(r, v)

    def _vector(self, n):
        return struct.unpack("<I", self.img[4 * n:4 * n + 4])[0]

    def timer_period_us(self, irq):
        base = TIMERS[irq]
        inten = self.regs.get(base + 0x304, 0)
        prescaler = self.regs.get(base + 0x510, 4)
        ccs = [self.regs.get(base + 0x540 + 4 * i, 0) for i in range(6) if inten >> (16 + i) & 1]
        ccs = [c for c in ccs if c]
        return min(ccs) / (16.0 / (1 << prescaler)) if ccs else None

    def advance(self, us, instructions_per_us=40):
        """Let `us` microseconds of mouse time go by."""
        end = self.time_us + us
        while self.time_us < end:
            if self.off:                                   # switched off: nothing runs until a wake-up
                self.time_us = end
                break
            if self._engine_used > self.ENGINE_LIFETIME_US:
                self.renew_engine()
            if self.wdt and self.time_us - self.wdt["fed"] > self.wdt["timeout"]:
                self.watchdog_resets += 1
                self._reboot("watchdog")
            nxt = min(end, self.time_us + 1000)
            for irq in TIMERS:
                period = self.timer_period_us(irq)
                if period:
                    self._due.setdefault(irq, self.time_us + period)
                    nxt = min(nxt, self._due[irq])
                else:
                    self._due.pop(irq, None)
            span = max(nxt - self.time_us, 1)
            try:
                self._run(int(span * instructions_per_us))
            except RuntimeError as e:
                if not self._fault(e):
                    raise
            self.time_us += span
            self._engine_used += span
            if self.off:
                continue
            for irq, due in list(self._due.items()):
                if due <= self.time_us:
                    self._raise_events(TIMERS[irq], 0x140, 0x158)
                    self.pending.add(irq)
                    self._due[irq] = due + (self.timer_period_us(irq) or 1e9)
            if self.time_us - self._last_ms >= 1000:
                self._last_ms = self.time_us
                for fn in self.every_ms:
                    fn()
                self._pwm_tick()
                for page, (_, irq) in PWM.items():         # (old fake) a running PWM finishes a sequence every ms
                    if page not in self.pwm and self.regs.get(page + 0x500):
                        self._raise_events(page, 0x104, 0x120)
                        self.pending.add(irq)
                for irq in RTCS:
                    self._raise_events(0x40000000 + (irq << 12), 0x100, 0x200)
                    self.pending.add(irq)
            try:
                self._deliver()
            except RuntimeError as e:
                if not self._fault(e):
                    raise

    def _fault(self, error) -> bool:
        """A crash. A real chip ends up restarting (fault handler or watchdog), so with
        fault_resets on that's what happens here too, and it gets written down."""
        if not self.fault_resets:
            return False
        self.faults.append((self.time_us, str(error)))
        self._reboot("crash")
        return True

    def _deliver(self):
        if self.nvic_pending:
            self.pending |= {b for b in range(64) if self.nvic_pending >> b & 1}
            self.nvic_pending = 0
        todo = {i for i in self.pending if self.nvic_on >> i & 1}
        self.pending = set()
        for irq in sorted(todo):
            handler = self._vector(16 + irq)
            if handler & ~1 != self._vector(2) & ~1:       # skip "nothing here" handlers
                self._call(handler)

    # save / go back, so one boot can be reused for many tests

    def save(self):
        uc = self.uc
        return dict(flash=self.ram(0, 0x100000), ram=self.ram(0x20000000, 0x40000),
                    uicr=self.ram(0x10000000, 0x2000), cpu=[uc.reg_read(r) for r in SAVED],
                    system=[uc.reg_read(r) for r in SYSTEM], pending=set(self.pending),
                    pc=self.pc, regs=dict(self.regs), scs=dict(self.scs), nvic=(self.nvic_on, self.nvic_pending),
                    due=dict(self._due), time=(self.time_us, self._last_ms), pins=dict(self.pins_in),
                    usb=self.usb_power, reboots=self.reboots, off=self.off,
                    wdt=dict(self.wdt) if self.wdt else None, clocks=dict(self.clocks), sd_events=list(self.sd_events),
                    sensor=copy.deepcopy(self.sensor), pwm=copy.deepcopy(self.pwm))

    def load(self, s, keep_counts=False):
        """Go back to a saved state. The counters (erases, resets...) start from zero again unless keep_counts."""
        uc = self.uc
        uc.mem_write(0, s["flash"]); uc.mem_write(0x20000000, s["ram"]); uc.mem_write(0x10000000, s["uicr"])
        for r, v in zip(SYSTEM, s.get("system", [])):
            uc.reg_write(r, v)
        for r, v in zip(SAVED, s["cpu"]):
            uc.reg_write(r, v)
        self.pc = s["pc"]; self.regs = dict(s["regs"]); self.scs = dict(s["scs"])
        self.nvic_on, self.nvic_pending = s["nvic"]; self._due = dict(s["due"])
        self.time_us, self._last_ms = s["time"]; self.pins_in = dict(s["pins"])
        self.usb_power = s["usb"]; self.reboots = s["reboots"]
        self.off = s.get("off", False); self.wdt = dict(s["wdt"]) if s.get("wdt") else None
        self.clocks = dict(s.get("clocks", {"hf": True, "lf": True}))
        self.sd_events = list(s.get("sd_events", []))
        self.pwm = copy.deepcopy(s["pwm"]) if "pwm" in s else self.pwm
        self.sensor = copy.deepcopy(s["sensor"]) if "sensor" in s else PixartSensor()
        self._detect = self._detect_now()
        if keep_counts:
            self.pending = set(s.get("pending", ()))
            return
        self.pending = set()
        self.erases.clear(); self.erase_log.clear(); self.bad_flash_writes.clear()
        self.sleeps = self.wakes = self.watchdog_resets = 0
        self.reset_log.clear()
        self.faults.clear()

    # reading things back

    def ram(self, addr, n):
        return bytes(self.uc.mem_read(addr, n))

    def poke(self, addr, data: bytes):
        self.uc.mem_write(addr, data)

    def led_pins(self):
        """{"PWM0": ["P0.14", ...]} for every PWM the firmware hooked up to pins."""
        def name(v):
            return None if v >> 31 else f"P{(v >> 5) & 1}.{v & 31:02}"
        return {k: [name(v) for v in pins if not v >> 31] for k, pins in self.pwm_pins.items()}

    def pwm_output(self, pwm="PWM0"):
        """Duty values (0-255) the PWM is currently putting on its first 3 pins."""
        page = next(p for p, (n, _) in PWM.items() if n == pwm)
        ptr = self.regs.get(page + 0x520, 0)
        if not ptr:
            return None
        return tuple(v & 0x7FFF for v in struct.unpack("<3H", self.ram(ptr, 6)))

    def pwm_setup(self, pwm="PWM0"):
        page = next(p for p, (n, _) in PWM.items() if n == pwm)
        return dict(top=self.regs.get(page + 0x508), prescaler=self.regs.get(page + 0x50C),
                    mode=self.regs.get(page + 0x510))
