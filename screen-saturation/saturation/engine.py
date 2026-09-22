"""Moteur de saturation via Windows Magnification API (par écran)."""

from __future__ import annotations

import sys
import threading
import time
from typing import Optional

from .matrix import identity_matrix, saturation_matrix
from .monitors import Monitor


class SaturationEngine:
    """Applique une saturation sur un moniteur précis.

    Mode *per-monitor* : fenêtre Magnifier plein écran sur l'écran choisi
    + MagSetColorEffect (ne touche pas les autres écrans).

    Mode *fullscreen* : MagSetFullscreenColorEffect (tous les écrans).
    """

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("Cet outil fonctionne uniquement sur Windows.")

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
            raise OSError("MagInitialize a échoué (pilote WDDM requis).")

        self._hwnd_host: int = 0
        self._hwnd_mag: int = 0
        self._active_monitor: Optional[Monitor] = None
        self._saturation: float = 1.0
        self._mode: str = "monitor"  # "monitor" | "all"
        self._running = True
        self._lock = threading.Lock()
        self._refresh_thread = threading.Thread(
            target=self._refresh_loop, name="mag-refresh", daemon=True
        )
        self._refresh_thread.start()

    def _ensure_dpi_aware(self) -> None:
        # Mesures correctes multi-écrans / scaling Windows
        ctypes = self._ctypes
        try:
            # Windows 10+ Per-Monitor V2
            ctx = ctypes.c_void_p(-4)
            self._user32.SetProcessDpiAwarenessContext(ctx)
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

        # LRESULT = pointer-sized signed int (x64 safe)
        self._WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        WM_DESTROY = 0x0002
        WM_CLOSE = 0x0010
        if msg in (WM_DESTROY, WM_CLOSE):
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

        self._wndproc_ref = self._WNDPROC(self._wnd_proc)  # keep alive
        wc = WNDCLASS()
        wc.style = 0
        wc.lpfnWndProc = self._wndproc_ref
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = self._kernel32.GetModuleHandleW(None)
        wc.hIcon = 0
        wc.hCursor = 0
        wc.hbrBackground = 0
        wc.lpszMenuName = None
        wc.lpszClassName = "DebunkPCSaturationHost"
        self._kernel32.SetLastError(0)
        atom = self._user32.RegisterClassW(ctypes.byref(wc))
        # 1410 = ERROR_CLASS_ALREADY_EXISTS (ok on relance)
        err = ctypes.get_last_error()
        if not atom and err not in (0, 1410):
            raise OSError(f"RegisterClassW a échoué (err={err})")

    def _create_monitor_windows(self, monitor: Monitor) -> None:
        ctypes = self._ctypes
        wintypes = self._wintypes

        self._destroy_monitor_windows()
        self._register_host_class()

        WS_EX_TOPMOST = 0x00000008
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_NOACTIVATE = 0x08000000
        WS_POPUP = 0x80000000
        WS_CHILD = 0x40000000
        WS_VISIBLE = 0x10000000
        HWND_TOPMOST = -1
        SWP_SHOWWINDOW = 0x0040
        SWP_NOACTIVATE = 0x0010
        MS_SHOWMAGNIFIEDCURSOR = 0x0001

        ex_style = (
            WS_EX_TOPMOST
            | WS_EX_LAYERED
            | WS_EX_TRANSPARENT
            | WS_EX_TOOLWINDOW
            | WS_EX_NOACTIVATE
        )

        self._hwnd_host = int(
            self._user32.CreateWindowExW(
                ex_style,
                "DebunkPCSaturationHost",
                "DebunkPC Saturation",
                WS_POPUP | WS_VISIBLE,
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
            raise OSError("Création de la fenêtre hôte impossible.")

        self._user32.SetWindowPos(
            self._hwnd_host,
            HWND_TOPMOST,
            monitor.left,
            monitor.top,
            monitor.width,
            monitor.height,
            SWP_SHOWWINDOW | SWP_NOACTIVATE,
        )

        self._hwnd_mag = int(
            self._user32.CreateWindowExW(
                0,
                "Magnifier",
                "MagChild",
                WS_CHILD | WS_VISIBLE | MS_SHOWMAGNIFIEDCURSOR,
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
            raise OSError(
                "Création du contrôle Magnifier impossible. "
                "Vérifie que le service d'accessibilité Windows est OK."
            )

        # Zoom 1:1 (on ne grossit pas, on colore seulement)
        transform = self._MAGTRANSFORM()
        transform.v[0] = 1.0
        transform.v[4] = 1.0
        transform.v[8] = 1.0
        self._mag.MagSetWindowTransform(
            self._hwnd_mag, ctypes.byref(transform)
        )

        # Exclure nos fenêtres pour éviter la boucle visuelle
        MW_FILTERMODE_EXCLUDE = 0
        hwnds = (wintypes.HWND * 2)(self._hwnd_host, self._hwnd_mag)
        self._mag.MagSetWindowFilterList(
            self._hwnd_mag, MW_FILTERMODE_EXCLUDE, 2, hwnds
        )

        self._update_source(monitor)
        self._apply_color_to_mag()

    def _update_source(self, monitor: Monitor) -> None:
        rect = self._RECT(
            monitor.left, monitor.top, monitor.right, monitor.bottom
        )
        self._mag.MagSetWindowSource(self._hwnd_mag, rect)

    def _apply_color_to_mag(self) -> None:
        if not self._hwnd_mag:
            return
        if abs(self._saturation - 1.0) < 1e-6:
            # NULL retire l'effet
            ok = self._mag.MagSetColorEffect(self._hwnd_mag, None)
        else:
            arr = self._ColorMatrix(*saturation_matrix(self._saturation))
            ok = self._mag.MagSetColorEffect(
                self._hwnd_mag, self._ctypes.byref(arr)
            )
        if not ok:
            raise OSError("MagSetColorEffect a échoué.")

    def _apply_fullscreen_effect(self) -> None:
        values = (
            identity_matrix()
            if abs(self._saturation - 1.0) < 1e-6
            else saturation_matrix(self._saturation)
        )
        arr = self._ColorMatrix(*values)
        ok = self._mag.MagSetFullscreenColorEffect(self._ctypes.byref(arr))
        if not ok:
            raise OSError("MagSetFullscreenColorEffect a échoué.")

    def _clear_fullscreen_effect(self) -> None:
        # Matrice identité = reset propre
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
        """Le Magnifier doit être rafraîchi pour suivre le contenu de l'écran."""
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
        """Applique la saturation.

        Args:
            saturation: 0.0 gris → 1.0 normal → 2.0 très saturé
            monitor: écran cible (requis si all_monitors=False)
            all_monitors: si True, effet global (ignore monitor)
        """
        with self._lock:
            self._saturation = float(saturation)
            if all_monitors:
                self._mode = "all"
                self._destroy_monitor_windows()
                self._active_monitor = None
                self._apply_fullscreen_effect()
                return

            if monitor is None:
                raise ValueError("Sélectionne un écran, ou active 'Tous les écrans'.")

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
        """Retire tout effet de saturation."""
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
