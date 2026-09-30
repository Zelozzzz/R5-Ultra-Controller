"""The mice Dorsal knows.

The R5, M5, R6 and R8 come from the same factory (JXC) and speak the same protocol.
Their official app's config only differs in the USB ids, so that's most of what's in
here for them.

The rest are other brands whose official web hub is the same software as Attack
Shark's and marks them with the same protocol (IsNewProtocol 1, like the R5). Their
limits (max DPI, stages, lift-off, polling rates per receiver) are copied from that
hub config. Dorsal should work with them, but nobody has tried one yet. Six LAMZU
mice have their firmware on that hub and get the same LED patch as the R5 (the hub's
.hex is what you pick in the installer, see firmware.py). The others have none.
"""

from __future__ import annotations

from dataclasses import dataclass

VID = 0x373E

CABLE = (125, 250, 500, 1000)
ALL = (125, 250, 500, 1000, 2000, 4000, 8000)
FROM_500 = (500, 1000, 2000, 4000, 8000)
FROM_1000 = (1000, 2000, 4000, 8000)


@dataclass(frozen=True)
class Model:
    key: str                  # used in file names
    name: str
    wired_pid: int
    dongle_pid: int | None
    bootloader_pid: int | None   # None = no firmware Dorsal can flash for it. Same USB vendor id as the mouse itself
    app_folder: str           # web/Config/<this>/ in the official Attack Shark app, "" for other brands
    firmware_file: str | None  # regex for its mouse firmware inside app.asar
    competitive: bool = True   # R6 firmware turns it down (0xA3, found on the virtual mouse), R8 doesn't list it
    dpi_button: bool = True    # the R6 has none (you map one), the R8 can't be checked without its firmware
    competitive_since: str | None = None   # firmware version that added Competitive Mode, if it came later
    brand: str = "Attack Shark"
    vid: int = VID
    more_receivers: tuple[int, ...] = ()   # other receivers it pairs with (1K, 4K)
    dpi_max: int = 42000
    stages: int = 6            # most DPI stages the DPI button can go through
    lift_off: tuple[str, ...] = ("0.7 mm", "1 mm", "2 mm")
    debounce: tuple[int, int] = (20, 1)   # max ms, step
    polling_cable: tuple[int, ...] = CABLE
    polling_receiver: tuple[int, ...] = ALL
    polling_by_receiver: tuple[tuple[int, tuple[int, ...]], ...] = ()   # receivers with their own list
    tried: str = ""            # "your mouse", "virtual mouse", or "" = nobody has tried it yet
    photo: str | None = None   # its top-view picture on the official web hub, see device_image.HUB
    protocol: str = "jxc"      # "jxc" = Attack Shark's (JXC factory). others have a module: compx.py, ipi.py
    more_cables: tuple[int, ...] = ()      # other USB ids it has on the cable (the IPI Float has three)
    live_lighting: bool = True # False: every color change is a flash write on the mouse (F1 Air), so no animated effects
    led_built_in: bool = False # its DPI light can stay on with a normal setting, no firmware needed (F1 Air)
    # where its LED window is when the picture doesn't show it: (center x, center y, width, height) as parts of
    # the mouse in the picture. the F1 Air's hub picture is a plain render, the real one has a slit there
    led_spot: tuple[float, float, float, float] | None = None
    # the DPI values its sensor really has, as (up to this DPI, step). () = any value. A typed number gets
    # moved onto one, so Dorsal shows what the mouse will actually hold
    dpi_steps: tuple[tuple[int, int], ...] = ()
    # minutes of sleep time it can hold (0 = never). None = all the app offers, () = it can't be set
    sleep_minutes: tuple[int, ...] | None = None
    debounce_min: int = 0                    # the X11 takes 4 ms and up
    no_settings: tuple[str, ...] = ()        # settings it doesn't have ("lod", "motion_sync"): not sent, not shown
    has_battery: bool = True                 # False: it only pushes a charge level as a message, there's nothing to read
    has_firmware_readback: bool = True       # False: no version Dorsal knows how to ask for
    flash_readback: bool = True              # False: flashed on a real one without reading the blocks back, so it stays that way
    vendor_flash: bool = False               # True: flashed with the bytes its maker's own tool sends, not the R5's way (flasher.py)

    def fit_dpi(self, dpi: int, low: int = 100) -> int:
        """`dpi` inside this mouse's limits and on a value its sensor has."""
        dpi = max(low, min(self.dpi_max, int(dpi)))
        for limit, step in self.dpi_steps:
            if dpi <= limit:
                return max(low, min(self.dpi_max, (dpi + step // 2) // step * step))
        return dpi

    @property
    def pids(self) -> tuple[int, ...]:
        return tuple(p for p in (self.wired_pid, *self.more_cables, self.dongle_pid, *self.more_receivers) if p is not None)

    def is_cable(self, pid: int | None) -> bool:
        return pid == self.wired_pid or pid in self.more_cables

    @property
    def ids(self) -> tuple[tuple[int, int], ...]:
        return tuple((self.vid, p) for p in self.pids)

    @property
    def has_firmware(self) -> bool:
        return self.bootloader_pid is not None

    @property
    def firmware_from_hub(self) -> bool:
        """It has firmware Dorsal can flash, but not inside the official Attack Shark app: the stock .hex
        comes from its brand's web hub and you pick it yourself (the LAMZU ones)."""
        return self.has_firmware and self.firmware_file is None

    def polling_for(self, pid: int | None) -> tuple[int, ...]:
        """Polling rates it offers over the cable or through this receiver."""
        if self.is_cable(pid):
            return self.polling_cable
        return dict(self.polling_by_receiver).get(pid, self.polling_receiver)


R5_ULTRA = Model("r5ultra", "R5 Ultra", 0x0046, 0x0047, 0xB046, "R5Ultra",
                 r"JXC_R5_Ultra_8K_Mouse_840_APP_.*\.hex$", tried="your mouse", photo="AttackShark/R5Ultra/Device_1.png",
                 flash_readback=False)      # it flashed fine on a real R5 without reading anything back, so it still does
M5_ULTRA = Model("m5ultra", "M5 Ultra", 0x0051, 0x0050, 0xB051, "M5Ultra",
                 r"JXC_M5_Ultra_8K_Mouse_840_APP_.*\.hex$", tried="virtual mouse", photo="AttackShark/M5Ultra/Device_1.png",
                 vendor_flash=True)
R6 = Model("r6", "R6", 0x0021, 0x0022, 0xB021, "R6",
           r"XMG_R6_8K_Mouse_840_APP_.*\.hex$", competitive=False, dpi_button=False,
           competitive_since="0.0.3.1", tried="virtual mouse", photo="AttackShark/R6/Device_1.png",   # v0.0.3.1 on the web hub added it, found on the virtual mouse
           vendor_flash=True)
R8 = Model("r8", "R8", 0x003A, 0x003B, None, "R8", None, competitive=False,   # official config: TrackModeEnable 0
           dpi_button=False, photo="AttackShark/R8/Device_1.png")

ATTACK_SHARK = (R5_ULTRA, M5_ULTRA, R6, R8)


# each mouse's top-view picture on its brand's web hub (same kind as Attack Shark's Device_1.png).
# WLMOUSE's hub has the plain edition as Device_255 (Device_1 is a special edition), LAMZU the
# other way round (its Device_255 is the Fnatic one). Picked by looking at them
PHOTOS = {
    "crdrako-ko-one": "CRDRAKO/TD013/Device_255.png",
    "lamzu-maya-x": "LAMZU/MayaX/Device_1.png",
    "lamzu-tachi": "LAMZU/TACHI/Device_1.png",
    "lamzu-inca": "LAMZU/INCA/Device_1.png",
    "lamzu-maya": "LAMZU/Maya/Device_1.png",
    "lamzu-paro": "LAMZU/PARO/Device_1.png",
    "lamzu-thorn": "LAMZU/THORN/Device_1.png",
    "lamzu-thorn-v2": "LAMZU/THORN/Device_1.png",
    "lamzu-tachi-lite": "LAMZU/TACHI_LITE/Device_1.png",
    "lamzu-mayax-v2": "LAMZU/MayaXV2/Device_1.png",
    "lamzu-atlantis": "LAMZU/Atlantis/Device_1.png",
    "lamzu-atlantis-og-champion": "LAMZU/AtlantisOG/Device_1.png",
    "lamzu-atlantis-mini": "LAMZU/AtlantisMini/Device_1.png",
    "lamzu-maya-m-54h20": "LAMZU/MayaM/Device_1.png",
    "lamzu-thorn-v2-54h20-0030": "LAMZU/THORNV2/Device_1.png",
    "lamzu-thorn-v2-54h20-0040": "LAMZU/THORNV2_3955/Device_1.png",
    "lamzu-dm198-54h20": "LAMZU/DM198/Device_1.png",
    "lamzu-dm198-op-54h20": "LAMZU/DM198_OP/Device_1.png",
    "lamzu-maya-x-54h20": "LAMZU/MayaX/Device_1.png",
    "lamzu-maya-54h20": "LAMZU/Maya/Device_1.png",
    "lamzu-atlantis-mini-54h20": "LAMZU/Atlantis/Device_1.png",
    "lamzu-orcus": "LAMZU/ORCUS/Device_1.png",
    "lamzu-maya-x-lm20": "LAMZU/MayaX(LM20)/Device_1.png",
    "lamzu-mini-lm20": "LAMZU/Lamzu_mini(LM20)/Device_255.png",
    "lamzu-maya-m-lm20": "LAMZU/MayaM(LM20)/Device_1.png",
    "lamzu-maya-lm20": "LAMZU/Maya(LM20)/Device_1.png",
    "lamzu-orcus-v2-lm20": "LAMZU/ORCUSV2(LM20)/Device_1.png",
    "unius-black-lotus": "BlackLotus/TD009/Device_1.png",
    "rawm-leviathan-v4-gt": "Rawm/V4GT/Device_255.png",
    "wlmouse-huan": "WL2/WLX_HUAN/Device_255.png",
    "wlmouse-huan-m": "WL2/WLX_HUANM/Device_255.png",
    "wlmouse-beast-miao": "WL2/WLX_MIAO/Device_255.png",
    "wlmouse-strider": "WL2/WLX_STRIDER/Device_255.png",
    "wlmouse-ying": "WL2/WL_YING/Device_255.png",
    "wlmouse-sword-x": "WL2/WL_SWORD_X/Device_255.png",
    "wlmouse-beast-mini": "WL2/WL/Device_255.png",
    "wlmouse-beast-mini-pro": "WL2/WL_MINI_PRO/Device_255.png",
    "wlmouse-beast-max": "WL2/WLX_MAX/Device_255.png",
    "wlmouse-beast-x": "WL2/WLX_EID/Device_255.png",
    "wlmouse-beast-x-pro": "WL2/WL_X_PRO/Device_255.png",
    "wlmouse-beast-g": "WL2/WL_G/Device_255.png",
    "wlmouse-beast-x-v2": "WL2/WL_X_V2/Device_255.png",
}


# where the LED dot or slit is in the picture, (x, y, width, height) as fractions of the mouse, measured on the
# pictures that show it lit. Dorsal paints it dark and lights it in your color
LED_SPOTS = {
    "lamzu-paro": (0.5, 0.498, 0.07, 0.016),
    "lamzu-atlantis": (0.5, 0.505, 0.098, 0.026),
    "lamzu-atlantis-mini-54h20": (0.5, 0.505, 0.098, 0.026),
    "lamzu-atlantis-mini": (0.507, 0.494, 0.075, 0.013),
    "lamzu-mini-lm20": (0.509, 0.496, 0.07, 0.009),
}


def _same(brand, name, key, vid, wired, receivers, dpi_max, stages, lift, cable, receiver,
          by_receiver=(), debounce=(20, 1), bootloader=None) -> Model:
    """A mouse from another brand's hub on the same protocol. Numbers straight from its hub config
    (`bootloader` is its DeviceBLPID there, the vendor id is the same as the mouse's)."""
    return Model(key, name, wired, receivers[0], bootloader, "", None, competitive=False, brand=brand, vid=vid,
                 more_receivers=tuple(receivers[1:]), dpi_max=dpi_max, stages=stages,
                 lift_off=tuple(f"{x} mm" for x in lift.split()), debounce=debounce,
                 polling_cable=cable, polling_receiver=receiver, polling_by_receiver=tuple(by_receiver),
                 photo=PHOTOS.get(key), led_spot=LED_SPOTS.get(key),
                 vendor_flash=bootloader is not None)   # the ones with a bootloader are the LAMZU six from LAMZU's hub


# from the hubs at xvalleyinno.top: CRDRAKO PANEL, LAMZU Aurora, UNIUS MOUSE HUB, RAWM HUB, WL MOUSE HUB.
# the MAMBASNAKE hub's M5 Ultra has the same USB ids as Attack Shark's, so it's the M5 Ultra above.
# none of these list Competitive Mode (TrackModeEnable) in their config
SAME_PROTOCOL = (
    # CRDRAKO
    _same("CRDRAKO", "KO-ONE", "crdrako-ko-one", 0x373E, 0x006A, (0x006B,), 30000, 5, "0.7 1 2", ALL, ALL),
    # LAMZU
    _same("LAMZU", "Maya X", "lamzu-maya-x", 0x373E, 0x001C, (0x001E, 0x001D), 30000, 5, "0.7 1 2", CABLE, FROM_1000,
          by_receiver=((0x001D, CABLE), (0x001E, FROM_500)), bootloader=0xB01C),
    _same("LAMZU", "Tachi", "lamzu-tachi", 0x37B0, 0x0005, (0x000C, 0x000B), 30000, 5, "0.7 1 2", CABLE, FROM_1000,
          by_receiver=((0x000B, CABLE), (0x000C, FROM_500)), bootloader=0x0006),
    _same("LAMZU", "Inca", "lamzu-inca", 0x37B0, 0x0009, (0x0010, 0x000F), 30000, 5, "0.7 1 2", CABLE, FROM_1000,
          by_receiver=((0x000F, CABLE), (0x0010, FROM_500)), bootloader=0x000A),
    _same("LAMZU", "Maya", "lamzu-maya", 0x37B0, 0x0011, (0x0015, 0x0013), 30000, 5, "0.7 1 2", CABLE, FROM_1000,
          by_receiver=((0x0013, CABLE), (0x0015, FROM_500)), bootloader=0x0012),
    _same("LAMZU", "Paro", "lamzu-paro", 0x37B0, 0x0007, (0x000E, 0x000D), 30000, 5, "0.7 1 2", CABLE, FROM_1000,
          by_receiver=((0x000D, CABLE), (0x000E, FROM_500)), bootloader=0x0008),
    _same("LAMZU", "Thorn", "lamzu-thorn", 0x37B0, 0x0017, (0x001B, 0x0019), 30000, 5, "0.7 1 2", CABLE, FROM_1000,
          by_receiver=((0x0019, CABLE), (0x001B, FROM_500)), bootloader=0x0018),
    _same("LAMZU", "Thorn V2", "lamzu-thorn-v2", 0x37B0, 0x0021, (0x0023, 0x0003), 30000, 5, "0.7 1 2", CABLE, FROM_1000,
          by_receiver=((0x0023, FROM_500),)),
    _same("LAMZU", "Tachi Lite", "lamzu-tachi-lite", 0x37B0, 0x001C, (0x001E,), 30000, 5, "0.7 1 2", CABLE, FROM_1000,
          by_receiver=((0x001E, FROM_500),)),
    _same("LAMZU", "Maya X V2", "lamzu-mayax-v2", 0x37B0, 0x001F, (0x0016, 0x00FF), 30000, 5, "0.7 1 2", CABLE, FROM_1000,
          by_receiver=((0x0016, FROM_500),)),
    _same("LAMZU", "Atlantis", "lamzu-atlantis", 0x3554, 0xF50F, (0xF510, 0xF50D), 30000, 5, "0.7 1 2", CABLE, FROM_1000,
          by_receiver=((0xF50D, CABLE), (0xF510, (125, 500, 1000, 2000, 4000, 8000)))),
    _same("LAMZU", "Atlantis OG Champion", "lamzu-atlantis-og-champion", 0x37B0, 0x0025, (0x0027,), 30000, 5, "0.7 1 2",
          CABLE, FROM_1000, by_receiver=((0x0027, FROM_500),)),
    _same("LAMZU", "Atlantis Mini", "lamzu-atlantis-mini", 0x37B0, 0x0028, (0x002A, 0x002B), 30000, 5, "0.7 1 2",
          CABLE, FROM_1000, by_receiver=((0x002B, CABLE), (0x002A, FROM_500))),
    _same("LAMZU", "Maya M (54H20)", "lamzu-maya-m-54h20", 0x37B0, 0x002C, (0x002E,), 30000, 5, "0.7 1 2", FROM_500, FROM_500),
    _same("LAMZU", "Thorn V2 (54H20)", "lamzu-thorn-v2-54h20-0030", 0x37B0, 0x0030, (0x0032,), 50000, 5, "0.7 1 2",
          FROM_500, FROM_500),
    _same("LAMZU", "Thorn V2 (54H20, 0040)", "lamzu-thorn-v2-54h20-0040", 0x37B0, 0x0040, (0x002E,), 50000, 5, "0.7 1 2",
          FROM_500, FROM_500),
    _same("LAMZU", "DM198 (54H20)", "lamzu-dm198-54h20", 0x37B0, 0x0034, (0x0036,), 30000, 5, "0.7 1 2", FROM_500, FROM_500),
    _same("LAMZU", "DM198 OP (54H20)", "lamzu-dm198-op-54h20", 0x37B0, 0x0038, (0x0036,), 30000, 5, "0.7 1 2",
          FROM_500, FROM_500),
    _same("LAMZU", "Maya X (54H20)", "lamzu-maya-x-54h20", 0x37B0, 0x003A, (0x003B,), 30000, 5, "0.7 1 2", FROM_500, FROM_500),
    _same("LAMZU", "Maya (54H20)", "lamzu-maya-54h20", 0x37B0, 0x003C, (0x0036,), 30000, 5, "0.7 1 2", FROM_500, FROM_500),
    _same("LAMZU", "Atlantis Mini (54H20)", "lamzu-atlantis-mini-54h20", 0x37B0, 0x003E, (0x003F,), 30000, 5, "0.7 1 2",
          FROM_500, (125, 500, 1000, 2000, 4000, 8000)),
    _same("LAMZU", "Orcus", "lamzu-orcus", 0x37B0, 0x0042, (0x0036,), 50000, 5, "0.7 1 2", FROM_500, FROM_500),
    _same("LAMZU", "Maya X (LM20)", "lamzu-maya-x-lm20", 0x37B0, 0x0044, (0x0048,), 50000, 5, "0.7 1 2", FROM_500, FROM_500),
    _same("LAMZU", "Mini (LM20)", "lamzu-mini-lm20", 0x37B0, 0x0046, (0x0048, 0x0054), 50000, 5, "0.7 1 2", FROM_500, FROM_500),
    _same("LAMZU", "Maya M (LM20)", "lamzu-maya-m-lm20", 0x37B0, 0x0052, (0x0048,), 50000, 5, "0.7 1 2", FROM_500, FROM_500),
    _same("LAMZU", "Maya (LM20)", "lamzu-maya-lm20", 0x37B0, 0x0050, (0x0048,), 50000, 5, "0.7 1 2", FROM_500, FROM_500),
    _same("LAMZU", "Orcus V2 (LM20)", "lamzu-orcus-v2-lm20", 0x37B0, 0x0056, (0x0048,), 50000, 5, "0.7 1 2", FROM_500, FROM_500),
    # UNIUS
    _same("UNIUS", "Black Lotus", "unius-black-lotus", 0x373E, 0x003C, (0x003D,), 26000, 5, "1 2", (500, 1000), FROM_500,
          debounce=(18, 2)),
    # RAWM
    _same("RAWM", "Leviathan V4 GT", "rawm-leviathan-v4-gt", 0x373E, 0x0098, (0x0099,), 45000, 6, "0.7 1 2", ALL, ALL),
    # WLMOUSE. 0xA882 is one 1K receiver several of them share
    _same("WLMOUSE", "Huan", "wlmouse-huan", 0x36A7, 0xA864, (0xA863,), 30000, 6, "0.7 1 2", ALL, ALL),
    _same("WLMOUSE", "Huan M", "wlmouse-huan-m", 0x36A7, 0xA859, (0xA863,), 50000, 6, "0.7 1 2", ALL, ALL),
    _same("WLMOUSE", "Beast Miao", "wlmouse-beast-miao", 0x36A7, 0xA867, (0xA866, 0xA882), 30000, 6, "0.7 1 2", CABLE, ALL,
          by_receiver=((0xA882, CABLE),)),
    _same("WLMOUSE", "Strider", "wlmouse-strider", 0x36A7, 0xA873, (0xA872, 0xA882), 30000, 6, "0.7 1 2", CABLE, ALL,
          by_receiver=((0xA882, CABLE),)),
    _same("WLMOUSE", "Ying", "wlmouse-ying", 0x36A7, 0xA875, (0xA874, 0xA882), 30000, 6, "0.7 1 2", CABLE, ALL,
          by_receiver=((0xA882, CABLE),)),
    _same("WLMOUSE", "Sword X", "wlmouse-sword-x", 0x36A7, 0xA879, (0xA878, 0xA882), 30000, 6, "0.7 1 2", CABLE, ALL,
          by_receiver=((0xA882, CABLE),)),
    _same("WLMOUSE", "Beast Mini", "wlmouse-beast-mini", 0x36A7, 0xA886, (0xA885, 0xA882), 26000, 6, "1 2", CABLE, ALL,
          by_receiver=((0xA882, CABLE),)),
    _same("WLMOUSE", "Beast Mini Pro", "wlmouse-beast-mini-pro", 0x36A7, 0xA869, (0xA868, 0xA882), 30000, 6, "0.7 1 2",
          CABLE, ALL, by_receiver=((0xA882, CABLE),)),
    _same("WLMOUSE", "Beast Max", "wlmouse-beast-max", 0x36A7, 0xA881, (0xA880, 0xA882), 30000, 6, "0.7 1 2", CABLE, ALL,
          by_receiver=((0xA882, CABLE),)),
    _same("WLMOUSE", "Beast X", "wlmouse-beast-x", 0x36A7, 0xA884, (0xA883, 0xA882), 26000, 6, "1 2", CABLE, ALL,
          by_receiver=((0xA882, CABLE),)),
    _same("WLMOUSE", "Beast X Pro", "wlmouse-beast-x-pro", 0x36A7, 0xA871, (0xA870, 0xA882), 30000, 6, "0.7 1 2", CABLE, ALL,
          by_receiver=((0xA882, CABLE),)),
    _same("WLMOUSE", "Beast G", "wlmouse-beast-g", 0x36A7, 0xA861, (0xA860, 0xA882), 30000, 6, "0.7 1 2", ALL, ALL,
          by_receiver=((0xA882, CABLE),)),
    _same("WLMOUSE", "Beast X V2", "wlmouse-beast-x-v2", 0x36A7, 0xA857, (0xA856,), 50000, 6, "0.7 1 2", ALL, ALL),
)

# other protocols, each with its own module (see device.ForeignMouse)
IPI_FLOAT_88 = Model("ipi-float-88", "Float 88", 0x1015, 0x1014, None, "", None, competitive=False, brand="IPI",
                     vid=0x372E, more_cables=(0x1028, 0x1056), dpi_max=26000, stages=6, lift_off=("1 mm", "2 mm"),
                     polling_cable=ALL, polling_receiver=ALL, protocol="ipi",
                     # IPI's app keeps a color per DPI stage for it, so it probably has a DPI light. Colors go into
                     # the settings table and nobody knows if that wears the mouse's flash, so no animated effects
                     live_lighting=False, dpi_steps=((26000, 50),), sleep_minutes=(),
                     photo="https://shan.ipigame.cn/src/assets/mouse/IPI_PIAO.png")   # ipi.py, from IPI's web driver
# Attack Shark's second platform, the MOUSE HUB web driver (controlhub.top), see compx.py. Model number
# 20 in that hub's config, PAW3955. Nobody has tried it here
F1_AIR = Model("f1air", "F1 Air", 0xF515, 0xFB44, None, "", None, competitive=False, vid=0x3554,
               more_cables=(0xF516,), more_receivers=(0xF517, 0xFB43, 0xFB35), dpi_max=60000, stages=6,
               lift_off=("0.7 mm", "0.9 mm", "1.2 mm", "1.4 mm", "1.6 mm"), debounce=(15, 1),
               polling_cable=ALL, polling_receiver=ALL, protocol="compx", live_lighting=False, led_built_in=True,
               dpi_steps=((42000, 1), (60000, 2)),      # every DPI up to 42000, even ones above
               sleep_minutes=(1, 2, 5, 10),             # its table goes from 10 s to 15 min, no 30 min and no never
               photo="https://controlhub.top/AttackShark/img/devices/mouse/7c14.png",   # the hub's picture, cid 7c mid 14
               led_spot=(0.5, 0.39, 0.014, 0.055))   # measured on Attack Shark's store photos, lit: on the button gap
# the same platform's X11 Ultra: model number 11 in that hub's config, PAW3950 (lift-off 0.7 / 1 / 2 mm, DPI in
# steps of 50 up to 30000 and 100 above). Same USB ids as the F1 Air, the mouse itself says which one it is.
# MontyMcK's Linux driver was checked on a real one. Nobody has tried it here. The hub's picture for model 11 is
# 7c0b (hex of cid 124 and mid 11, like the F1 Air's 7c14): the black forged-carbon shell Attack Shark sells the
# X11 Ultra with, and its cyan LED slit is drawn in, so Dorsal lights that like the R6's
X11_ULTRA = Model("x11ultra", "X11 Ultra", 0xF515, 0xFB44, None, "", None, competitive=False, vid=0x3554,
                  more_cables=(0xF516,), more_receivers=(0xF517, 0xFB43, 0xFB35), dpi_max=42000, stages=6,
                  lift_off=("0.7 mm", "1 mm", "2 mm"), debounce=(15, 1), polling_cable=ALL, polling_receiver=ALL,
                  protocol="compx", live_lighting=False, led_built_in=True,
                  dpi_steps=((30000, 50), (42000, 100)), sleep_minutes=(1, 2, 5, 10),
                  photo="https://controlhub.top/AttackShark/img/devices/mouse/7c0b.png",
                  led_spot=(0.5, 0.493, 0.062, 0.02))       # measured on the picture, its LED slit lit
# Attack Shark's third platform: the X series on vendor 1D57 (xseries.py). The old X11, on its cable only: its
# receiver 1D57:FA60 is shared with other brands' mice, so Dorsal doesn't look at it. The DPI codes are the ones
# the vendor's software and its web hub write (320 captured packets and the hub's own encoder agree on the 310
# Dorsal sends). The driver that was tested on a real X11 writes other bytes for 110 of them, so those have no
# real-mouse evidence. Nobody has tried Dorsal on one. No lift-off, motion sync or sleep setting that Dorsal
# understands, so those aren't offered, and it has no battery or firmware reading to give
X11 = Model("x11", "X11", 0xFA55, None, None, "", None, competitive=False, vid=0x1D57, dpi_max=22000, stages=6,
            lift_off=("1 mm",), debounce=(50, 2), debounce_min=4, polling_cable=CABLE, polling_receiver=CABLE,
            protocol="xseries", live_lighting=False, led_built_in=True,
            dpi_steps=((10000, 50), (20000, 100), (22000, 200)), sleep_minutes=(),
            no_settings=("lod", "motion_sync"), has_battery=False, has_firmware_readback=False,
            # the picture on the vendor's web hub (szslxd-tech.com, the one Attack Shark's driver page links to).
            # Its file name has a hash in it, if the hub is rebuilt this stops working and Dorsal draws the mouse
            photo="https://szslxd-tech.com/assets/X11-DpjEREMO.png", led_spot=(0.494, 0.485, 0.07, 0.014))
OTHER_PROTOCOLS = (IPI_FLOAT_88, F1_AIR, X11_ULTRA, X11)

MODELS = ATTACK_SHARK + SAME_PROTOCOL + OTHER_PROTOCOLS
DEFAULT = R5_ULTRA
VIDS = tuple(sorted({m.vid for m in MODELS}))
ALL_IDS = tuple(dict.fromkeys(i for m in MODELS for i in m.ids))
ALL_PIDS = tuple(dict.fromkeys(pid for m in MODELS for pid in m.pids))


def by_ids(vid: int, pid: int, prefer: Model | None = None) -> Model | None:
    """The mouse with this USB id. A receiver some mice share goes to `prefer` if it's one of them."""
    found = [m for m in MODELS if (vid, pid) in m.ids]
    if prefer is not None and prefer in found:
        return prefer
    return found[0] if found else None


def by_pid(pid: int, prefer: Model | None = None) -> Model | None:
    """By product id alone, for the Attack Shark vendor id (the firmware installer only knows those)."""
    return by_ids(VID, pid, prefer)


def by_key(key: str | None) -> Model | None:
    return next((m for m in MODELS if m.key == key), None)
