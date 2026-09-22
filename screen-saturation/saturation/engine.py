"""Facade — choisit le backend compatible plein écran exclusif en priorité."""

from __future__ import annotations

import sys
from typing import Optional

from .backends.base import BackendInfo, SaturationBackend
from .grading import PRESETS, GradeParams, vibrance_to_saturation_factor
from .monitors import Monitor


def _try_backends() -> tuple[SaturationBackend, list[str]]:
    logs: list[str] = []

    try:
        from .backends.nvidia import NvidiaVibranceBackend

        backend = NvidiaVibranceBackend()
        logs.append(f"OK: {backend.info().name}")
        return backend, logs
    except Exception as exc:
        logs.append(f"NVIDIA: {exc}")

    try:
        from .backends.amd import AmdSaturationBackend

        backend = AmdSaturationBackend()
        logs.append(f"OK: {backend.info().name}")
        return backend, logs
    except Exception as exc:
        logs.append(f"AMD: {exc}")

    try:
        from .backends.magnification import MagnificationBackend

        backend = MagnificationBackend()
        logs.append(f"OK (secours): {backend.info().name}")
        return backend, logs
    except Exception as exc:
        logs.append(f"Magnifier: {exc}")

    raise OSError("Aucun backend disponible.\n" + "\n".join(logs))


class SaturationEngine:
    """API unique pour l'UI."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("Cet outil fonctionne uniquement sur Windows.")
        self._backend, self._init_logs = _try_backends()

    @property
    def backend_info(self) -> BackendInfo:
        return self._backend.info()

    @property
    def init_logs(self) -> list[str]:
        return list(self._init_logs)

    def apply_grade(
        self,
        params: GradeParams,
        monitor: Optional[Monitor] = None,
        all_monitors: bool = False,
    ) -> None:
        apply_grade = getattr(self._backend, "apply_grade", None)
        if callable(apply_grade):
            apply_grade(params, monitor, all_monitors)
            return
        # AMD / Magnifier : approx via vibrance douce uniquement
        self._backend.apply(
            vibrance_to_saturation_factor(params.vibrance),
            monitor,
            all_monitors,
        )

    def apply_preset(
        self,
        name: str,
        monitor: Optional[Monitor] = None,
        all_monitors: bool = False,
    ) -> None:
        if name not in PRESETS:
            raise ValueError(f"Preset inconnu: {name}")
        self.apply_grade(PRESETS[name], monitor, all_monitors)

    def apply(
        self,
        saturation: float,
        monitor: Optional[Monitor] = None,
        all_monitors: bool = False,
    ) -> None:
        self._backend.apply(saturation, monitor, all_monitors)

    def reset(self) -> None:
        self._backend.reset()

    def close(self) -> None:
        self._backend.close()
