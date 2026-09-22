"""Backend NVIDIA — grading naturel (LUT gamma pilote + DVC léger).

Compatible plein écran exclusif via :
  - NvAPI_DISP_SetTargetGammaCorrection (LUT 1024, pipeline NVIDIA)
  - Digital Vibrance seulement en appoint (faible), pas en effet principal
"""

from __future__ import annotations

import sys
from typing import Optional

from ..grading import GradeParams, build_gamma_lut_1024, vibrance_to_saturation_factor
from ..monitors import Monitor
from .base import BackendInfo, SaturationBackend

_NVAPI_IDS = {
    "Initialize": 0x0150E828,
    "Unload": 0xD22BDD7E,
    "EnumNvidiaDisplayHandle": 0x9ABDD40D,
    "GetAssociatedNvidiaDisplayHandle": 0x35C29134,
    "GetAssociatedDisplayOutputId": 0xD995937E,
    "GetDVCInfoEx": 0x0E45002D,
    "SetDVCLevelEx": 0x4A82C2B1,
    "SetDVCLevel": 0x172409B4,
    "SetTargetGammaCorrection": 0x7082A053,
    "GetErrorMessage": 0x6C2D048C,
}

NVAPI_OK = 0
NV_GAMMARAMP_VALUES = 1024


class NvidiaVibranceBackend(SaturationBackend):
    """Grading NVIDIA — présence/courbes d'abord, vibrance en second."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("Windows uniquement.")

        import ctypes

        self._ctypes = ctypes
        self._fns: dict = {}
        self._original_dvc: dict[int, int] = {}
        self._display_ids: dict[int, int] = {}  # nvHandle -> displayId
        self._gamma_ok = False

        dll_name = "nvapi64.dll" if ctypes.sizeof(ctypes.c_void_p) == 8 else "nvapi.dll"
        try:
            self._dll = ctypes.WinDLL(dll_name)
        except OSError as exc:
            raise OSError(f"NVIDIA NVAPI introuvable ({dll_name}).") from exc

        query = self._dll.nvapi_QueryInterface
        query.restype = ctypes.c_void_p
        query.argtypes = [ctypes.c_uint]

        required = [
            "Initialize",
            "Unload",
            "GetAssociatedNvidiaDisplayHandle",
            "GetDVCInfoEx",
            "SetDVCLevelEx",
        ]
        for name in required:
            ptr = query(_NVAPI_IDS[name])
            if not ptr:
                raise OSError(f"NVAPI {name} indisponible.")
            self._fns[name] = ptr

        # Optionnels
        for name in (
            "EnumNvidiaDisplayHandle",
            "GetAssociatedDisplayOutputId",
            "SetDVCLevel",
            "SetTargetGammaCorrection",
        ):
            ptr = query(_NVAPI_IDS[name])
            if ptr:
                self._fns[name] = ptr

        status = self._cfun("Initialize", ctypes.c_int, [])()
        if status != NVAPI_OK:
            raise OSError(f"NvAPI_Initialize a échoué (status={status}).")

        self._gamma_ok = "SetTargetGammaCorrection" in self._fns and (
            "GetAssociatedDisplayOutputId" in self._fns
        )
        if not self._enum_handles():
            # encore OK si GetAssociated marche plus tard
            pass

    def info(self) -> BackendInfo:
        detail = (
            "Courbes gamma NVIDIA (présence naturelle) + vibrance légère — "
            "plein écran exclusif OK."
            if self._gamma_ok
            else "Digital Vibrance NVIDIA — plein écran exclusif OK (LUT gamma indisponible)."
        )
        return BackendInfo(
            name="DebunkPC Natural (NVIDIA)",
            exclusive_fullscreen=True,
            detail=detail,
        )

    def _cfun(self, name: str, restype, argtypes):
        ctypes = self._ctypes
        return ctypes.CFUNCTYPE(restype, *argtypes)(self._fns[name])

    def _enum_handles(self) -> list[int]:
        if "EnumNvidiaDisplayHandle" not in self._fns:
            return []
        ctypes = self._ctypes
        fn = self._cfun(
            "EnumNvidiaDisplayHandle",
            ctypes.c_int,
            [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)],
        )
        handles: list[int] = []
        for i in range(16):
            h = ctypes.c_void_p()
            if fn(i, ctypes.byref(h)) != NVAPI_OK:
                break
            handles.append(int(h.value or 0))
        return handles

    def _handle_for_monitor(self, monitor: Monitor) -> int:
        ctypes = self._ctypes
        fn = self._cfun(
            "GetAssociatedNvidiaDisplayHandle",
            ctypes.c_int,
            [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)],
        )
        h = ctypes.c_void_p()
        status = fn(monitor.name.encode("ascii", errors="ignore"), ctypes.byref(h))
        if status != NVAPI_OK or not h.value:
            raise OSError(
                f"Écran NVIDIA introuvable pour {monitor.name} (status={status})."
            )
        return int(h.value)

    def _display_id(self, handle: int) -> int:
        if handle in self._display_ids:
            return self._display_ids[handle]
        if "GetAssociatedDisplayOutputId" not in self._fns:
            raise OSError("GetAssociatedDisplayOutputId indisponible.")
        ctypes = self._ctypes
        fn = self._cfun(
            "GetAssociatedDisplayOutputId",
            ctypes.c_int,
            [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)],
        )
        out = ctypes.c_uint32()
        status = fn(ctypes.c_void_p(handle), ctypes.byref(out))
        if status != NVAPI_OK:
            raise OSError(f"GetAssociatedDisplayOutputId a échoué ({status}).")
        self._display_ids[handle] = int(out.value)
        return int(out.value)

    def _get_dvc(self, handle: int) -> tuple[int, int, int, int]:
        ctypes = self._ctypes

        class INFO(ctypes.Structure):
            _fields_ = [
                ("version", ctypes.c_uint32),
                ("currentLevel", ctypes.c_int32),
                ("minLevel", ctypes.c_int32),
                ("maxLevel", ctypes.c_int32),
                ("defaultLevel", ctypes.c_int32),
            ]

        info = INFO()
        info.version = ctypes.sizeof(INFO) | (1 << 16)
        fn = self._cfun(
            "GetDVCInfoEx",
            ctypes.c_int,
            [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(INFO)],
        )
        status = fn(ctypes.c_void_p(handle), 0, ctypes.byref(info))
        if status != NVAPI_OK:
            raise OSError(f"GetDVCInfoEx a échoué ({status}).")
        return (
            int(info.currentLevel),
            int(info.minLevel),
            int(info.maxLevel),
            int(info.defaultLevel),
        )

    def _set_dvc(self, handle: int, level: int) -> None:
        ctypes = self._ctypes
        _, min_l, max_l, default_l = self._get_dvc(handle)
        level = max(min_l, min(max_l, int(level)))

        class INFO(ctypes.Structure):
            _fields_ = [
                ("version", ctypes.c_uint32),
                ("currentLevel", ctypes.c_int32),
                ("minLevel", ctypes.c_int32),
                ("maxLevel", ctypes.c_int32),
                ("defaultLevel", ctypes.c_int32),
            ]

        info = INFO()
        info.version = ctypes.sizeof(INFO) | (1 << 16)
        info.currentLevel = level
        info.minLevel = min_l
        info.maxLevel = max_l
        info.defaultLevel = default_l
        fn = self._cfun(
            "SetDVCLevelEx",
            ctypes.c_int,
            [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(INFO)],
        )
        status = fn(ctypes.c_void_p(handle), 0, ctypes.byref(info))
        if status != NVAPI_OK and "SetDVCLevel" in self._fns:
            fn2 = self._cfun(
                "SetDVCLevel",
                ctypes.c_int,
                [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int],
            )
            status = fn2(ctypes.c_void_p(handle), 0, level)
        if status != NVAPI_OK:
            raise OSError(f"SetDVC a échoué ({status}).")

    def _set_gamma(self, handle: int, params: GradeParams) -> None:
        if not self._gamma_ok:
            return
        ctypes = self._ctypes
        display_id = self._display_id(handle)
        lut = build_gamma_lut_1024(params)

        class NV_GAMMA_CORRECTION_EX(ctypes.Structure):
            _fields_ = [
                ("version", ctypes.c_uint32),
                ("gammaRampEx", ctypes.c_float * (3 * NV_GAMMARAMP_VALUES)),
                ("unknown", ctypes.c_uint32),
            ]

        corr = NV_GAMMA_CORRECTION_EX()
        corr.version = ctypes.sizeof(NV_GAMMA_CORRECTION_EX) | (1 << 16)
        corr.unknown = 1
        for i, (r, g, b) in enumerate(lut):
            corr.gammaRampEx[i * 3 + 0] = r
            corr.gammaRampEx[i * 3 + 1] = g
            corr.gammaRampEx[i * 3 + 2] = b

        fn = self._cfun(
            "SetTargetGammaCorrection",
            ctypes.c_int,
            [ctypes.c_uint32, ctypes.POINTER(NV_GAMMA_CORRECTION_EX)],
        )
        status = fn(ctypes.c_uint32(display_id), ctypes.byref(corr))
        if status != NVAPI_OK:
            raise OSError(
                f"SetTargetGammaCorrection a échoué ({status}). "
                "Mise à jour du pilote NVIDIA recommandée."
            )

    def _reset_gamma(self, handle: int) -> None:
        self._set_gamma(handle, GradeParams())  # identité

    @staticmethod
    def _sat_to_dvc(sat: float, min_l: int, max_l: int, default_l: int) -> int:
        sat = max(0.0, min(2.0, float(sat)))
        if sat <= 1.0:
            return int(round(min_l + (default_l - min_l) * sat))
        return int(round(default_l + (max_l - default_l) * (sat - 1.0)))

    def _remember_dvc(self, handle: int) -> None:
        if handle not in self._original_dvc:
            cur, _, _, _ = self._get_dvc(handle)
            self._original_dvc[handle] = cur

    def apply_grade(
        self,
        params: GradeParams,
        monitor: Optional[Monitor],
        all_monitors: bool,
    ) -> None:
        handles = self._resolve_handles(monitor, all_monitors)
        sat = vibrance_to_saturation_factor(params.vibrance)
        for handle in handles:
            self._remember_dvc(handle)
            _, min_l, max_l, default_l = self._get_dvc(handle)
            level = self._sat_to_dvc(sat, min_l, max_l, default_l)
            self._set_dvc(handle, level)
            if self._gamma_ok:
                self._set_gamma(handle, params)

    def apply(
        self,
        saturation: float,
        monitor: Optional[Monitor],
        all_monitors: bool,
    ) -> None:
        # Compat ancienne API : saturation seule → grade minimal + vibrance
        v = 0.0
        if saturation <= 1.0:
            v = max(0.0, (saturation - 0.85) / (1.0 - 0.85)) * 0.5
        else:
            v = 0.5 + (saturation - 1.0) / (1.25 - 1.0) * 0.5
        v = max(0.0, min(1.0, v))
        self.apply_grade(
            GradeParams(presence=0.25, vibrance=v, gamma=1.0),
            monitor,
            all_monitors,
        )

    def _resolve_handles(
        self, monitor: Optional[Monitor], all_monitors: bool
    ) -> list[int]:
        if all_monitors:
            handles = self._enum_handles()
            if not handles:
                raise OSError("Aucun écran NVIDIA.")
            return handles
        if monitor is None:
            raise ValueError("Sélectionne un écran.")
        return [self._handle_for_monitor(monitor)]

    def reset(self) -> None:
        for handle, original in list(self._original_dvc.items()):
            try:
                self._set_dvc(handle, original)
            except OSError:
                pass
            if self._gamma_ok:
                try:
                    self._reset_gamma(handle)
                except OSError:
                    pass
        self._original_dvc.clear()

    def close(self) -> None:
        try:
            self.reset()
        except Exception:
            pass
        try:
            self._cfun("Unload", self._ctypes.c_int, [])()
        except Exception:
            pass


# Alias rétrocompat
NvidiaNaturalBackend = NvidiaVibranceBackend
