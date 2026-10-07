"""Spotting a Lunii that is plugged in but has not mounted anything.

Detection proper works off the mounted filesystem, which is what the engine
reads and writes. But a device that is connected without being switched on
enumerates over USB and mounts nothing, and "no Lunii connected" is a poor way
to describe that. Asking the operating system what is on the bus turns a silence
into an instruction.
"""

import platform
import re
import subprocess

# The vendor and product identifiers Lunii hardware reports.
LUNII_VID = 0x0483
KNOWN_PIDS = {0x6820, 0xA341}
LUNII_VID_V1 = 0x0C45


def _macos():
    output = subprocess.run(
        ["ioreg", "-p", "IOUSB", "-l", "-w", "0"],
        capture_output=True, text=True, timeout=10,
    ).stdout
    if '"USB Vendor Name" = "Lunii"' in output:
        return True
    return any(f'"idVendor" = {vid}' in output for vid in (LUNII_VID, LUNII_VID_V1))


def _linux():
    from pathlib import Path

    for entry in Path("/sys/bus/usb/devices").glob("*/idVendor"):
        try:
            vendor = int(entry.read_text().strip(), 16)
        except (OSError, ValueError):
            continue
        if vendor in (LUNII_VID, LUNII_VID_V1):
            return True
    return False


def _windows():
    script = (
        "Get-CimInstance Win32_PnPEntity | "
        "Where-Object { $_.DeviceID -like '*VID_0483*' -or $_.DeviceID -like '*VID_0C45*' } | "
        "Select-Object -First 1 -ExpandProperty DeviceID"
    )
    output = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True, text=True, timeout=15,
    ).stdout
    return bool(re.search(r"VID_(0483|0C45)", output, re.IGNORECASE))


def is_lunii_attached():
    """True when Lunii hardware is on the USB bus, mounted or not.

    Any failure answers ``False``: this only ever refines a message, and must
    never be the reason a transfer does not happen.
    """
    probe = {"Darwin": _macos, "Linux": _linux, "Windows": _windows}.get(platform.system())
    if probe is None:
        return False
    try:
        return probe()
    except Exception:
        return False
