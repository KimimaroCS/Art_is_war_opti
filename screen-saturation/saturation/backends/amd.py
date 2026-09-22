"""Backend AMD — saturation ADL (compatible plein écran exclusif)."""

from __future__ import annotations

import sys
from typing import Optional

from ..monitors import Monitor
from .base import BackendInfo, SaturationBackend

ADL_OK = 0
ADL_DISPLAY_COLOR_SATURATION = 1 << 2
ADL_MAX_PATH = 256


class AmdSaturationBackend(SaturationBackend):
    """Saturation via atiadlxx.dll — niveau pilote, OK en exclusif."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("Windows uniquement.")

        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        self._buffers: list = []
        self._context = ctypes.c_void_p()
        self._originals: dict[tuple[int, int], int] = {}
        self._display_map: dict[str, tuple[int, int]] = {}

        try:
            self._dll = ctypes.WinDLL("atiadlxx.dll")
        except OSError:
            try:
                self._dll = ctypes.WinDLL("atiadlxy.dll")
            except OSError as exc:
                raise OSError("AMD ADL introuvable (atiadlxx.dll).") from exc

        AllocFunc = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_int)

        def _malloc(size: int):
            buf = (ctypes.c_byte * size)()
            self._buffers.append(buf)
            return ctypes.cast(buf, ctypes.c_void_p).value

        self._alloc_cb = AllocFunc(_malloc)

        # Prefer ADL2
        if hasattr(self._dll, "ADL2_Main_Control_Create"):
            self._dll.ADL2_Main_Control_Create.argtypes = [
                AllocFunc,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_void_p),
            ]
            self._dll.ADL2_Main_Control_Create.restype = ctypes.c_int
            status = self._dll.ADL2_Main_Control_Create(
                self._alloc_cb, 1, ctypes.byref(self._context)
            )
            self._use_adl2 = True
        else:
            self._dll.ADL_Main_Control_Create.argtypes = [AllocFunc, ctypes.c_int]
            self._dll.ADL_Main_Control_Create.restype = ctypes.c_int
            status = self._dll.ADL_Main_Control_Create(self._alloc_cb, 1)
            self._use_adl2 = False

        if status != ADL_OK:
            raise OSError(f"ADL_Main_Control_Create a échoué ({status}).")

        self._setup_prototypes()
        self._rebuild_display_map()
        if not self._display_map:
            self.close()
            raise OSError("Aucun écran AMD détecté via ADL.")

    def info(self) -> BackendInfo:
        return BackendInfo(
            name="AMD Saturation (ADL)",
            exclusive_fullscreen=True,
            detail="Réglage pilote GPU — compatible plein écran exclusif.",
        )

    def _setup_prototypes(self) -> None:
        ctypes = self._ctypes

        class AdapterInfo(ctypes.Structure):
            _fields_ = [
                ("iSize", ctypes.c_int),
                ("iAdapterIndex", ctypes.c_int),
                ("strUDID", ctypes.c_char * ADL_MAX_PATH),
                ("iBusNumber", ctypes.c_int),
                ("iDeviceNumber", ctypes.c_int),
                ("iFunctionNumber", ctypes.c_int),
                ("iVendorID", ctypes.c_int),
                ("strAdapterName", ctypes.c_char * ADL_MAX_PATH),
                ("strDisplayName", ctypes.c_char * ADL_MAX_PATH),
                ("iPresent", ctypes.c_int),
                ("iExist", ctypes.c_int),
                ("strDriverPath", ctypes.c_char * ADL_MAX_PATH),
                ("strDriverPathExt", ctypes.c_char * ADL_MAX_PATH),
                ("strPNPString", ctypes.c_char * ADL_MAX_PATH),
                ("iOSDisplayIndex", ctypes.c_int),
            ]

        class ADLDisplayID(ctypes.Structure):
            _fields_ = [
                ("iDisplayLogicalIndex", ctypes.c_int),
                ("iDisplayPhysicalIndex", ctypes.c_int),
                ("iDisplayLogicalAdapterIndex", ctypes.c_int),
                ("iDisplayPhysicalAdapterIndex", ctypes.c_int),
            ]

        class ADLDisplayInfo(ctypes.Structure):
            _fields_ = [
                ("displayID", ADLDisplayID),
                ("iDisplayControllerIndex", ctypes.c_int),
                ("strDisplayName", ctypes.c_char * ADL_MAX_PATH),
                ("strDisplayManufacturerName", ctypes.c_char * ADL_MAX_PATH),
                ("iDisplayType", ctypes.c_int),
                ("iDisplayOutputType", ctypes.c_int),
                ("iDisplayConnector", ctypes.c_int),
                ("iDisplayInfoMask", ctypes.c_int),
                ("iDisplayInfoValue", ctypes.c_int),
            ]

        self._AdapterInfo = AdapterInfo
        self._ADLDisplayInfo = ADLDisplayInfo

        if self._use_adl2:
            self._dll.ADL2_Adapter_NumberOfAdapters_Get.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_int),
            ]
            self._dll.ADL2_Adapter_AdapterInfo_Get.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(AdapterInfo),
                ctypes.c_int,
            ]
            self._dll.ADL2_Display_DisplayInfo_Get.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.POINTER(ADLDisplayInfo)),
                ctypes.c_int,
            ]
            self._dll.ADL2_Display_Color_Get.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
            ]
            self._dll.ADL2_Display_Color_Set.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
            ]
            self._dll.ADL2_Main_Control_Destroy.argtypes = [ctypes.c_void_p]
        else:
            self._dll.ADL_Adapter_NumberOfAdapters_Get.argtypes = [
                ctypes.POINTER(ctypes.c_int)
            ]
            self._dll.ADL_Adapter_AdapterInfo_Get.argtypes = [
                ctypes.POINTER(AdapterInfo),
                ctypes.c_int,
            ]
            self._dll.ADL_Display_DisplayInfo_Get.argtypes = [
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.POINTER(ADLDisplayInfo)),
                ctypes.c_int,
            ]
            self._dll.ADL_Display_Color_Get.argtypes = [
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
            ]
            self._dll.ADL_Display_Color_Set.argtypes = [
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
            ]

    def _rebuild_display_map(self) -> None:
        """Mappe \\.\\DISPLAYx → (adapterIndex, displayLogicalIndex)."""
        ctypes = self._ctypes
        num = ctypes.c_int()
        if self._use_adl2:
            self._dll.ADL2_Adapter_NumberOfAdapters_Get(
                self._context, ctypes.byref(num)
            )
        else:
            self._dll.ADL_Adapter_NumberOfAdapters_Get(ctypes.byref(num))

        if num.value <= 0:
            return

        infos = (self._AdapterInfo * num.value)()
        for i in range(num.value):
            infos[i].iSize = ctypes.sizeof(self._AdapterInfo)

        if self._use_adl2:
            self._dll.ADL2_Adapter_AdapterInfo_Get(
                self._context, infos, ctypes.sizeof(infos)
            )
        else:
            self._dll.ADL_Adapter_AdapterInfo_Get(infos, ctypes.sizeof(infos))

        ADL_DISPLAY_DISPLAYINFO_DISPLAYCONNECTED = 0x00000001
        ADL_DISPLAY_DISPLAYINFO_DISPLAYMAPPED = 0x00000002

        seen_adapters: set[int] = set()
        for i in range(num.value):
            adapter = infos[i]
            if not adapter.iPresent:
                continue
            aidx = adapter.iAdapterIndex
            if aidx in seen_adapters:
                continue
            seen_adapters.add(aidx)

            gdi_name = adapter.strDisplayName.decode("ascii", errors="ignore")
            display_count = ctypes.c_int()
            displays_ptr = ctypes.POINTER(self._ADLDisplayInfo)()

            if self._use_adl2:
                status = self._dll.ADL2_Display_DisplayInfo_Get(
                    self._context,
                    aidx,
                    ctypes.byref(display_count),
                    ctypes.byref(displays_ptr),
                    0,
                )
            else:
                status = self._dll.ADL_Display_DisplayInfo_Get(
                    aidx,
                    ctypes.byref(display_count),
                    ctypes.byref(displays_ptr),
                    0,
                )
            if status != ADL_OK or not display_count.value:
                continue

            for d in range(display_count.value):
                info = displays_ptr[d]
                flags = info.iDisplayInfoValue
                if not (
                    flags
                    & (
                        ADL_DISPLAY_DISPLAYINFO_DISPLAYCONNECTED
                        | ADL_DISPLAY_DISPLAYINFO_DISPLAYMAPPED
                    )
                ):
                    continue
                didx = info.displayID.iDisplayLogicalIndex
                # Clé primaire : nom GDI de l'adapter (souvent le 1er écran)
                if gdi_name and gdi_name not in self._display_map:
                    self._display_map[gdi_name] = (aidx, didx)
                # Clé secondaire : index d'écran Windows-like
                key = f"#{len(self._display_map)}"
                self._display_map[key] = (aidx, didx)

    def _resolve(self, monitor: Monitor) -> tuple[int, int]:
        if monitor.name in self._display_map:
            return self._display_map[monitor.name]
        # Fallback : Nième écran de la map ordonnée
        values = [
            v
            for k, v in self._display_map.items()
            if not k.startswith("#")
        ]
        if not values:
            values = list({v for v in self._display_map.values()})
        if monitor.index < len(values):
            return values[monitor.index]
        raise OSError(f"Écran AMD introuvable pour {monitor.name}.")

    def _color_get(self, adapter: int, display: int) -> tuple[int, int, int, int]:
        ctypes = self._ctypes
        cur = ctypes.c_int()
        default = ctypes.c_int()
        mn = ctypes.c_int()
        mx = ctypes.c_int()
        step = ctypes.c_int()
        if self._use_adl2:
            status = self._dll.ADL2_Display_Color_Get(
                self._context,
                adapter,
                display,
                ADL_DISPLAY_COLOR_SATURATION,
                ctypes.byref(cur),
                ctypes.byref(default),
                ctypes.byref(mn),
                ctypes.byref(mx),
                ctypes.byref(step),
            )
        else:
            status = self._dll.ADL_Display_Color_Get(
                adapter,
                display,
                ADL_DISPLAY_COLOR_SATURATION,
                ctypes.byref(cur),
                ctypes.byref(default),
                ctypes.byref(mn),
                ctypes.byref(mx),
                ctypes.byref(step),
            )
        if status != ADL_OK:
            raise OSError(f"ADL_Display_Color_Get a échoué ({status}).")
        return cur.value, mn.value, mx.value, default.value

    def _color_set(self, adapter: int, display: int, value: int) -> None:
        if self._use_adl2:
            status = self._dll.ADL2_Display_Color_Set(
                self._context,
                adapter,
                display,
                ADL_DISPLAY_COLOR_SATURATION,
                int(value),
            )
        else:
            status = self._dll.ADL_Display_Color_Set(
                adapter, display, ADL_DISPLAY_COLOR_SATURATION, int(value)
            )
        if status != ADL_OK:
            raise OSError(f"ADL_Display_Color_Set a échoué ({status}).")

    @staticmethod
    def _saturation_to_level(sat: float, min_l: int, max_l: int, default_l: int) -> int:
        sat = max(0.0, min(2.0, float(sat)))
        if sat <= 1.0:
            return int(round(min_l + (default_l - min_l) * sat))
        return int(round(default_l + (max_l - default_l) * (sat - 1.0)))

    def _remember(self, key: tuple[int, int]) -> None:
        if key not in self._originals:
            cur, _, _, _ = self._color_get(*key)
            self._originals[key] = cur

    def apply(
        self,
        saturation: float,
        monitor: Optional[Monitor],
        all_monitors: bool,
    ) -> None:
        targets: list[tuple[int, int]]
        if all_monitors:
            targets = list({v for k, v in self._display_map.items() if not k.startswith("#")})
            if not targets:
                targets = list(set(self._display_map.values()))
        else:
            if monitor is None:
                raise ValueError("Sélectionne un écran.")
            targets = [self._resolve(monitor)]

        for key in targets:
            self._remember(key)
            _, mn, mx, default = self._color_get(*key)
            level = self._saturation_to_level(saturation, mn, mx, default)
            level = max(mn, min(mx, level))
            self._color_set(*key, level)

    def reset(self) -> None:
        for key, original in list(self._originals.items()):
            try:
                self._color_set(*key, original)
            except OSError:
                pass
        self._originals.clear()

    def close(self) -> None:
        try:
            self.reset()
        except Exception:
            pass
        try:
            if self._use_adl2:
                self._dll.ADL2_Main_Control_Destroy(self._context)
            elif hasattr(self._dll, "ADL_Main_Control_Destroy"):
                self._dll.ADL_Main_Control_Destroy()
        except Exception:
            pass
