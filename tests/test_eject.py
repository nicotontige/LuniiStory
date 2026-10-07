"""Unmounting the device, so it is never yanked mid-write."""

import subprocess

import pytest

from luniistory import eject


def _record(calls, returncode=0, stderr=""):
    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, returncode, stdout="", stderr=stderr)
    return run


def test_macos_asks_diskutil(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", _record(calls))
    eject._macos("/Volumes/LUNII")
    assert calls == [["diskutil", "eject", "/Volumes/LUNII"]]


def test_windows_targets_the_drive_letter(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", _record(calls))
    eject._windows("E:\\")
    assert "ParseName('E:')" in calls[0][-1]


def test_a_refusal_is_reported(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _record([], returncode=1, stderr="busy"))
    with pytest.raises(eject.EjectError, match="busy"):
        eject._macos("/Volumes/LUNII")


def test_an_unknown_platform_says_so(monkeypatch):
    monkeypatch.setattr(eject.platform, "system", lambda: "Haiku")
    with pytest.raises(eject.EjectError, match="Haiku"):
        eject.eject("/mnt/lunii")


def test_eject_dispatches_on_the_platform(monkeypatch):
    seen = []
    monkeypatch.setattr(eject.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(eject, "_macos", lambda path: seen.append(path))
    eject.eject("/Volumes/LUNII")
    assert seen == ["/Volumes/LUNII"]


def test_linux_prefers_udisks(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", _record(calls))
    monkeypatch.setattr(eject.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(eject, "_device_for", lambda path: "/dev/sdb1")
    eject._linux("/media/lunii")
    # udisks unmounts without privileges, which umount would need.
    assert calls == [["udisksctl", "unmount", "-b", "/dev/sdb1"]]
