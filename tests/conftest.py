import pytest


class NoUSB:
    """What `import hid` gives a test: a PC with nothing plugged in. Opening a device is a bug in the test."""

    @staticmethod
    def enumerate(vid=0, pid=0):
        return []

    class device:
        def __init__(self, *args, **kwargs):
            raise AssertionError("this test reached the real USB bus, give it a fake hid")


@pytest.fixture(autouse=True)
def _no_real_usb(monkeypatch):
    """No test may touch a real mouse, whether the PC has hidapi and a mouse plugged in or, like the CI runner, has
    no hidapi at all. The flasher is what writes firmware, so a test that gets as far as it without giving it a
    pretend hid fails outright. Everything else sees a PC with no mice. A test that means to use a pretend hid
    patches these again."""
    from dorsal import device, flasher

    def refuse():
        raise AssertionError("this test reached the real USB bus, give the flasher a fake hid")
    monkeypatch.setattr(flasher, "_hid", refuse)
    monkeypatch.setattr(device, "_hid", lambda: NoUSB)
