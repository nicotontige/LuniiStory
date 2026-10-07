"""Telling a Lunii that is off apart from one that is absent."""

import subprocess

import pytest

from luniistory import usb

IOREG_WITH_LUNII = '''
  +-o IOUSBHostDevice@01100000  <class IOUSBHostDevice>
      {
        "idProduct" = 41793
        "USB Vendor Name" = "Lunii"
        "idVendor" = 1155
      }
'''

IOREG_WITHOUT = '''
  +-o IOUSBHostDevice@01100000  <class IOUSBHostDevice>
      {
        "idProduct" = 1234
        "USB Vendor Name" = "Some Keyboard"
        "idVendor" = 9999
      }
'''


def _fake_run(output):
    def run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")
    return run


def test_lunii_on_the_bus_is_recognised(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run(IOREG_WITH_LUNII))
    assert usb._macos() is True


def test_other_hardware_is_not_a_lunii(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run(IOREG_WITHOUT))
    assert usb._macos() is False


def test_the_vendor_id_alone_is_enough(monkeypatch):
    """Firmware that reports no vendor string still reports its identifiers."""
    monkeypatch.setattr(subprocess, "run", _fake_run('"idVendor" = 1155'))
    assert usb._macos() is True


def test_a_failing_probe_answers_no(monkeypatch):
    def explode(*args, **kwargs):
        raise OSError("ioreg is not here")

    monkeypatch.setattr(subprocess, "run", explode)
    # This only ever refines a message; it must never raise into a transfer.
    assert usb.is_lunii_attached() is False


def test_an_unknown_platform_answers_no(monkeypatch):
    monkeypatch.setattr(usb.platform, "system", lambda: "Haiku")
    assert usb.is_lunii_attached() is False


@pytest.mark.parametrize("vendor", ["0483", "0c45"])
def test_linux_reads_the_vendor_from_sysfs(monkeypatch, tmp_path, vendor):
    devices = tmp_path / "sys" / "bus" / "usb" / "devices" / "1-1"
    devices.mkdir(parents=True)
    (devices / "idVendor").write_text(vendor + "\n")

    import luniistory.usb as module
    monkeypatch.setattr(module, "_linux", lambda: any(
        int(path.read_text().strip(), 16) in (module.LUNII_VID, module.LUNII_VID_V1)
        for path in devices.parent.glob("*/idVendor")
    ))
    assert module._linux() is True
