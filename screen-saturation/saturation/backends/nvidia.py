"""Backend NVIDIA — Digital Vibrance (compatible plein écran exclusif)."""

from __future__ import annotations

import sys
from typing import Optional

from ..monitors import Monitor
from .base import BackendInfo, SaturationBackend

# NvAPI_QueryInterface IDs (driver NVIDIA)
_NVAPI_IDS = {
    "Initialize": 0x0150E828,
    "Unload": 0xD22BDD7E,
    "EnumNvidiaDisplayHandle": 0x9ABDD40D,
    "GetAssociatedNvidiaDisplayHandle": 0x35C29134,
    "GetDVCInfoEx": 0x0E45002D,
    "SetDVCLevelEx": 0x4A82C2B1,
    "GetErrorMessage": 0x6C2D048C,
}

NVAPI_OK = 0


class NvidiaVibranceBackend(SaturationBackend):
    """Digital Vibrance via nvapi64.dll — survit au plein écran exclusif."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("Windows uniquement.")

        import ctypes

        self._ctypes = ctypes
        self._dll = None
        self._fns: dict = {}
        self._originals: dict[int, int] = {}  # handle -> niveau DVC d'origine
        self._touched: set[int] = set()

        dll_name = "nvapi64.dll" if ctypes.sizeof(ctypes.c_void_p) == 8 else "nvapi.dll"
        try:
            self._dll = ctypes.WinDLL(dll_name)
        except OSError as exc:
            raise OSError(f"NVIDIA NVAPI introuvable ({dll_name}).") from exc

        query = getattr(self._dll, "nvapi_QueryInterface", None)
        if query is None:
            raise OSError("nvapi_QueryInterface manquant.")
        query.restype = ctypes.c_void_p
        query.argtypes = [ctypes.c_uint]

        for name, iid in _NVAPI_IDS.items():
            ptr = query(iid)
            if not ptr:
                raise OSError(f"NVAPI {name} indisponible (id=0x{iid:X}).")
            self._fns[name] = ptr

        status = self._call("Initialize")
        if status != NVAPI_OK:
            raise OSError(f"NvAPI_Initialize a échoué (status={status}).")

        # Smoke test : au moins 1 display NVIDIA
        if self._enum_handles() is None and not self._probe_any_handle():
            self.close()
            raise OSError("Aucun écran NVIDIA détecté via NVAPI.")

    def info(self) -> BackendInfo:
        return BackendInfo(
            name="NVIDIA Digital Vibrance",
            exclusive_fullscreen=True,
            detail="Réglage pilote GPU — compatible plein écran exclusif.",
        )

    def _cfun(self, name: str, restype, argtypes):
        ctypes = self._ctypes
        proto = ctypes.CFUNCTYPE(restype, *argtypes)
        return proto(self._fns[name])

    def _call(self, name: str, *args) -> int:
        ctypes = self._ctypes
        # Signatures minimales à la volée
        if name == "Initialize":
            fn = self._cfun("Initialize", ctypes.c_int, [])
            return int(fn())
        if name == "Unload":
            fn = self._cfun("Unload", ctypes.c_int, [])
            return int(fn())
        raise ValueError(name)

    def _probe_any_handle(self) -> bool:
        return bool(self._enum_handles())

    def _enum_handles(self) -> list[int]:
        ctypes = self._ctypes
        fn = self._cfun(
            "EnumNvidiaDisplayHandle",
            ctypes.c_int,
            [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)],
        )
        handles: list[int] = []
        for i in range(16):
            h = ctypes.c_void_p()
            status = fn(i, ctypes.byref(h))
            if status != NVAPI_OK:
                break
            handles.append(h.value or 0)
        return handles

    def _handle_for_monitor(self, monitor: Monitor) -> int:
        ctypes = self._ctypes
        fn = self._cfun(
            "GetAssociatedNvidiaDisplayHandle",
            ctypes.c_int,
            [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)],
        )
        name = monitor.name.encode("ascii", errors="ignore")
        h = ctypes.c_void_p()
        status = fn(name, ctypes.byref(h))
        if status != NVAPI_OK or not h.value:
            raise OSError(
                f"Écran NVIDIA introuvable pour {monitor.name} "
                f"(status={status}). Branche-le sur le GPU NVIDIA ?"
            )
        return int(h.value)

    def _get_dvc(self, handle: int) -> tuple[int, int, int, int]:
        """Retourne (current, min, max, default)."""
        ctypes = self._ctypes

        class NV_DISPLAY_DVC_INFO_EX(ctypes.Structure):
            _fields_ = [
                ("version", ctypes.c_uint32),
                ("currentLevel", ctypes.c_int32),
                ("minLevel", ctypes.c_int32),
                ("maxLevel", ctypes.c_int32),
                ("defaultLevel", ctypes.c_int32),
            ]

        info = NV_DISPLAY_DVC_INFO_EX()
        # MAKE_NVAPI_VERSION(NV_DISPLAY_DVC_INFO_EX, 1) = size | (1 << 16)
        info.version = ctypes.sizeof(NV_DISPLAY_DVC_INFO_EX) | (1 << 16)

        fn = self._cfun(
            "GetDVCInfoEx",
            ctypes.c_int,
            [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(NV_DISPLAY_DVC_INFO_EX)],
        )
        status = fn(ctypes.c_void_p(handle), 0, ctypes.byref(info))
        if status != NVAPI_OK:
            raise OSError(f"GetDVCInfoEx a échoué (status={status}).")
        return (
            int(info.currentLevel),
            int(info.minLevel),
            int(info.maxLevel),
            int(info.defaultLevel),
        )

    def _set_dvc(self, handle: int, level: int) -> None:
        ctypes = self._ctypes
        current, min_l, max_l, default_l = self._get_dvc(handle)
        level = max(min_l, min(max_l, int(level)))

        class NV_DISPLAY_DVC_INFO_EX(ctypes.Structure):
            _fields_ = [
                ("version", ctypes.c_uint32),
                ("currentLevel", ctypes.c_int32),
                ("minLevel", ctypes.c_int32),
                ("maxLevel", ctypes.c_int32),
                ("defaultLevel", ctypes.c_int32),
            ]

        info = NV_DISPLAY_DVC_INFO_EX()
        info.version = ctypes.sizeof(NV_DISPLAY_DVC_INFO_EX) | (1 << 16)
        info.currentLevel = level
        info.minLevel = min_l
        info.maxLevel = max_l
        info.defaultLevel = default_l

        fn = self._cfun(
            "SetDVCLevelEx",
            ctypes.c_int,
            [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(NV_DISPLAY_DVC_INFO_EX)],
        )
        status = fn(ctypes.c_void_p(handle), 0, ctypes.byref(info))
        if status != NVAPI_OK:
            # Fallback : API DVC simple
            set_simple = self._cfun(
                "SetDVCLevel",
                ctypes.c_int,
                [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int],
            ) if "SetDVCLevel" in self._fns else None
            if set_simple is None:
                # Charger SetDVCLevel à la demande
                query = self._dll.nvapi_QueryInterface
                query.restype = ctypes.c_void_p
                query.argtypes = [ctypes.c_uint]
                ptr = query(0x172409B4)
                if not ptr:
                    raise OSError(f"SetDVCLevelEx a échoué (status={status}).")
                self._fns["SetDVCLevel"] = ptr
                set_simple = self._cfun(
                    "SetDVCLevel",
                    ctypes.c_int,
                    [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int],
                )
            status2 = set_simple(ctypes.c_void_p(handle), 0, level)
            if status2 != NVAPI_OK:
                raise OSError(
                    f"SetDVCLevelEx/SetDVCLevel a échoué "
                    f"(status={status}/{status2})."
                )

        _ = current  # lu pour cohérence API

    def _remember(self, handle: int) -> None:
        if handle not in self._originals:
            current, _, _, _ = self._get_dvc(handle)
            self._originals[handle] = current

    @staticmethod
    def _saturation_to_level(sat: float, min_l: int, max_l: int, default_l: int) -> int:
        """0→min, 1→default, 2→max."""
        sat = max(0.0, min(2.0, float(sat)))
        if sat <= 1.0:
            return int(round(min_l + (default_l - min_l) * sat))
        return int(round(default_l + (max_l - default_l) * (sat - 1.0)))

    def apply(
        self,
        saturation: float,
        monitor: Optional[Monitor],
        all_monitors: bool,
    ) -> None:
        handles: list[int]
        if all_monitors:
            handles = self._enum_handles()
            if not handles:
                raise OSError("Aucun écran NVIDIA à régler.")
        else:
            if monitor is None:
                raise ValueError("Sélectionne un écran.")
            handles = [self._handle_for_monitor(monitor)]

        for handle in handles:
            self._remember(handle)
            _, min_l, max_l, default_l = self._get_dvc(handle)
            level = self._saturation_to_level(saturation, min_l, max_l, default_l)
            self._set_dvc(handle, level)
            self._touched.add(handle)

    def reset(self) -> None:
        for handle, original in list(self._originals.items()):
            try:
                self._set_dvc(handle, original)
            except OSError:
                try:
                    _, _, _, default_l = self._get_dvc(handle)
                    self._set_dvc(handle, default_l)
                except OSError:
                    pass
        self._touched.clear()

    def close(self) -> None:
        try:
            self.reset()
        except Exception:
            pass
        try:
            self._call("Unload")
        except Exception:
            pass
