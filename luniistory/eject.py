"""Unmounting the Lunii before it is unplugged.

Pulling a USB disk out while the system still holds writes is how a device ends
up with half-written stories, which is exactly the state the empty folders on a
used Lunii suggest. Each system has its own way of saying "done with this".
"""

import platform
import shutil
import subprocess
from pathlib import Path

TIMEOUT = 30


class EjectError(Exception):
    pass


def _run(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=TIMEOUT)
    if result.returncode != 0:
        raise EjectError((result.stderr or result.stdout).strip() or " ".join(command))
    return result.stdout


def _macos(mount_point):
    _run(["diskutil", "eject", str(mount_point)])


def _linux(mount_point):
    # udisks unmounts without privileges when the volume was mounted for the
    # user, which is the normal case for a plugged-in device.
    if shutil.which("udisksctl"):
        source = _device_for(mount_point)
        if source:
            _run(["udisksctl", "unmount", "-b", source])
            return
    if shutil.which("eject"):
        _run(["eject", str(mount_point)])
        return
    _run(["umount", str(mount_point)])


def _device_for(mount_point):
    import psutil

    target = str(mount_point).rstrip("/")
    for partition in psutil.disk_partitions():
        if partition.mountpoint.rstrip("/") == target:
            return partition.device
    return None


def _windows(mount_point):
    drive = str(mount_point).rstrip("\\/")[:2]
    script = (
        "$shell = New-Object -comObject Shell.Application; "
        f"$shell.Namespace(17).ParseName('{drive}').InvokeVerb('Eject')"
    )
    _run(["powershell", "-NoProfile", "-Command", script])


def eject(mount_point):
    """Unmounts the volume. Raises :class:`EjectError` when it will not go."""
    handler = {"Darwin": _macos, "Linux": _linux, "Windows": _windows}.get(platform.system())
    if handler is None:
        raise EjectError(f"Ejecting is not supported on {platform.system()}")
    handler(mount_point)


def is_mounted(mount_point):
    return Path(mount_point).exists()
