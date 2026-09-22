"""Énumération des moniteurs Windows via ctypes."""

from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Monitor:
    index: int
    name: str
    handle: int
    left: int
    top: int
    right: int
    bottom: int
    is_primary: bool

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def label(self) -> str:
        primary = " (principal)" if self.is_primary else ""
        return f"Écran {self.index + 1} — {self.width}x{self.height}{primary}"


def list_monitors() -> list[Monitor]:
    """Retourne la liste des écrans connectés (Windows uniquement)."""
    if sys.platform != "win32":
        raise OSError("Cet outil fonctionne uniquement sur Windows.")

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", wintypes.WCHAR * 32),
        ]

    MONITORINFOF_PRIMARY = 0x00000001
    MonitorEnumProc = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )

    found: list[Monitor] = []

    def _callback(hmonitor, _hdc, _lprect, _lparam):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if not user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            return True
        idx = len(found)
        found.append(
            Monitor(
                index=idx,
                name=info.szDevice,
                handle=int(hmonitor),
                left=info.rcMonitor.left,
                top=info.rcMonitor.top,
                right=info.rcMonitor.right,
                bottom=info.rcMonitor.bottom,
                is_primary=bool(info.dwFlags & MONITORINFOF_PRIMARY),
            )
        )
        return True

    cb = MonitorEnumProc(_callback)
    if not user32.EnumDisplayMonitors(0, None, cb, 0):
        raise OSError("Impossible d'énumérer les moniteurs.")
    if not found:
        raise OSError("Aucun moniteur détecté.")
    return found
