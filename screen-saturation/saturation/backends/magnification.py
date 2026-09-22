"""Backend Magnification Windows — secours (PAS compatible plein écran exclusif)."""

from __future__ import annotations

import sys
import threading
import time
from typing import Optional

from ..matrix import identity_matrix, saturation_matrix
from ..monitors import Monitor
from .base import BackendInfo, SaturationBackend


class MagnificationBackend(SaturationBackend):
    """Filtre OS via Magnification API.

    Ne fonctionne en général PAS en plein écran exclusif.
    Conservé uniquement comme secours (Intel / pas de NVAPI/ADL).
    """

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("Windows uniquement.")

        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        self._wintypes = wintypes
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32
        self._mag = ctypes.windll.Magnification

        self._ensure_dpi_aware()
        self._setup_prototypes()

        if not self._mag.MagInitialize():
            raise OSError("MagInitialize a échoué.")

        self._hwnd_host = 0
        self._hwnd_mag = 0
        self._active_monitor: Optional[Monitor] = None
        self._saturation = 1.0
        self._mode = "monitor"
        self._running = True
        self._lock = threading.Lock()
        self._refresh_thread = threading.Thread(
            target=self._refresh_loop, name="mag-refresh", daemon=True
        )
        self._refresh_thread.start()

    def info(self) -> BackendInfo:
        return BackendInfo(
            name="Windows Magnifier (secours)",
            exclusive_fullscreen=False,
            detail="Filtre OS — incompatible plein écran exclusif. Passe en borderless.",
        )

    def _ensure_dpi_aware(self) -> None:
        ctypes = self._ctypes
        try:
            self._user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                self._user32.SetProcessDPIAware()

    def _setup_prototypes(self) -> None:
        ctypes = self._ctypes
        wintypes = self._wintypes
        self._ColorMatrix = ctypes.c_float * 25

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            ]

        class MAGTRANSFORM(ctypes.Structure):
            _fields_ = [("v", ctypes.c_float * 9)]

        self._RECT = RECT
        self._MAGTRANSFORM = MAGTRANSFORM
        self._mag.MagInitialize.restype = wintypes.BOOL
        self._mag.MagUninitialize.restype = wintypes.BOOL
        self._mag.MagSetFullscreenColorEffect.argtypes = [
            ctypes.POINTER(self._ColorMatrix)
        ]
        self._mag.MagSetFullscreenColorEffect.restype = wintypes.BOOL
        self._mag.MagSetColorEffect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(self._ColorMatrix),
        ]
        self._mag.MagSetColorEffect.restype = wintypes.BOOL
        self._mag.MagSetWindowSource.argtypes = [wintypes.HWND, RECT]
        self._mag.MagSetWindowSource.restype = wintypes.BOOL
        self._mag.MagSetWindowTransform.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(MAGTRANSFORM),
        ]
        self._mag.MagSetWindowTransform.restype = wintypes.BOOL
        self._mag.MagSetWindowFilterList.argtypes = [
            wintypes.HWND,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.POINTER(wintypes.HWND),
        ]
        self._mag.MagSetWindowFilterList.restype = wintypes.BOOL
        self._WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg in (0x0002, 0x0010):
            return 0
        return self._user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _register_host_class(self) -> None:
        ctypes = self._ctypes
        wintypes = self._wintypes

        class WNDCLASS(ctypes.Structure):
            _fields_ = [
                ("style", ctypes.c_uint),
                ("lpfnWndProc", self._WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        self._wndproc_ref = self._WNDPROC(self._wnd_proc)
        wc = WNDCLASS()
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = self._kernel32.GetModuleHandleW(None)
        wc.lpszClassName = "DebunkPCSaturationHost"
        self._kernel32.SetLastError(0)
        atom = self._user32.RegisterClassW(ctypes.byref(wc))
        err = ctypes.get_last_error()
        if not atom and err not in (0, 1410):
            raise OSError(f"RegisterClassW a échoué (err={err})")

    def _create_monitor_windows(self, monitor: Monitor) -> None:
        ctypes = self._ctypes
        wintypes = self._wintypes
        self._destroy_monitor_windows()
        self._register_host_class()

        ex_style = 0x00000008 | 0x00080000 | 0x00000020 | 0x00000080 | 0x08000000
        self._hwnd_host = int(
            self._user32.CreateWindowExW(
                ex_style,
                "DebunkPCSaturationHost",
                "DebunkPC Saturation",
                0x80000000 | 0x10000000,
                monitor.left,
                monitor.top,
                monitor.width,
                monitor.height,
                0,
                0,
                self._kernel32.GetModuleHandleW(None),
                None,
            )
        )
        if not self._hwnd_host:
            raise OSError("Création fenêtre hôte impossible.")

        self._user32.SetWindowPos(
            self._hwnd_host,
            -1,
            monitor.left,
            monitor.top,
            monitor.width,
            monitor.height,
            0x0040 | 0x0010,
        )

        self._hwnd_mag = int(
            self._user32.CreateWindowExW(
                0,
                "Magnifier",
                "MagChild",
                0x40000000 | 0x10000000 | 0x0001,
                0,
                0,
                monitor.width,
                monitor.height,
                self._hwnd_host,
                0,
                self._kernel32.GetModuleHandleW(None),
                None,
            )
        )
        if not self._hwnd_mag:
            self._destroy_monitor_windows()
            raise OSError("Création Magnifier impossible.")

        transform = self._MAGTRANSFORM()
        transform.v[0] = 1.0
        transform.v[4] = 1.0
        transform.v[8] = 1.0
        self._mag.MagSetWindowTransform(self._hwnd_mag, ctypes.byref(transform))
        hwnds = (wintypes.HWND * 2)(self._hwnd_host, self._hwnd_mag)
        self._mag.MagSetWindowFilterList(self._hwnd_mag, 0, 2, hwnds)
        self._update_source(monitor)
        self._apply_color_to_mag()

    def _update_source(self, monitor: Monitor) -> None:
        rect = self._RECT(monitor.left, monitor.top, monitor.right, monitor.bottom)
        self._mag.MagSetWindowSource(self._hwnd_mag, rect)

    def _apply_color_to_mag(self) -> None:
        if not self._hwnd_mag:
            return
        if abs(self._saturation - 1.0) < 1e-6:
            ok = self._mag.MagSetColorEffect(self._hwnd_mag, None)
        else:
            arr = self._ColorMatrix(*saturation_matrix(self._saturation))
            ok = self._mag.MagSetColorEffect(self._hwnd_mag, self._ctypes.byref(arr))
        if not ok:
            raise OSError("MagSetColorEffect a échoué.")

    def _apply_fullscreen_effect(self) -> None:
        values = (
            identity_matrix()
            if abs(self._saturation - 1.0) < 1e-6
            else saturation_matrix(self._saturation)
        )
        arr = self._ColorMatrix(*values)
        if not self._mag.MagSetFullscreenColorEffect(self._ctypes.byref(arr)):
            raise OSError("MagSetFullscreenColorEffect a échoué.")

    def _clear_fullscreen_effect(self) -> None:
        arr = self._ColorMatrix(*identity_matrix())
        self._mag.MagSetFullscreenColorEffect(self._ctypes.byref(arr))

    def _destroy_monitor_windows(self) -> None:
        if self._hwnd_mag:
            self._user32.DestroyWindow(self._hwnd_mag)
            self._hwnd_mag = 0
        if self._hwnd_host:
            self._user32.DestroyWindow(self._hwnd_host)
            self._hwnd_host = 0

    def _refresh_loop(self) -> None:
        while self._running:
            with self._lock:
                if (
                    self._mode == "monitor"
                    and self._hwnd_mag
                    and self._active_monitor is not None
                ):
                    try:
                        self._update_source(self._active_monitor)
                    except Exception:
                        pass
            time.sleep(1 / 60)

    def apply(
        self,
        saturation: float,
        monitor: Optional[Monitor] = None,
        all_monitors: bool = False,
    ) -> None:
        with self._lock:
            self._saturation = float(saturation)
            if all_monitors:
                self._mode = "all"
                self._destroy_monitor_windows()
                self._active_monitor = None
                self._apply_fullscreen_effect()
                return
            if monitor is None:
                raise ValueError("Sélectionne un écran.")
            self._mode = "monitor"
            self._clear_fullscreen_effect()
            if (
                self._active_monitor is None
                or self._active_monitor.handle != monitor.handle
                or not self._hwnd_mag
            ):
                self._create_monitor_windows(monitor)
                self._active_monitor = monitor
            else:
                self._active_monitor = monitor
                self._apply_color_to_mag()

    def reset(self) -> None:
        with self._lock:
            self._saturation = 1.0
            self._destroy_monitor_windows()
            self._active_monitor = None
            self._clear_fullscreen_effect()
            self._mode = "monitor"

    def close(self) -> None:
        self._running = False
        self.reset()
        try:
            self._mag.MagUninitialize()
        except Exception:
            pass
