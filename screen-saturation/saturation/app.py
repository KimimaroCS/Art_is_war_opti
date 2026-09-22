"""Interface Tkinter — presets de grading naturel (mieux que Digital Vibrance)."""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import messagebox, ttk

from .engine import SaturationEngine
from .grading import PRESETS, GradeParams
from .monitors import Monitor, list_monitors


class SaturationApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("DebunkPC — Color Grade")
        self.geometry("460x620")
        self.minsize(420, 580)
        self.configure(bg="#0E1116")

        self._engine: SaturationEngine | None = None
        self._monitors: list[Monitor] = []

        self._build_style()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        try:
            self._engine = SaturationEngine()
            self._reload_monitors()
            self._update_backend_badge()
            self._live_var.set(True)
            if not self._engine.backend_info.exclusive_fullscreen:
                messagebox.showwarning(
                    "Plein écran exclusif",
                    "Backend Magnifier détecté.\n"
                    "Pas compatible plein écran exclusif — NVIDIA/AMD requis.",
                )
        except OSError as exc:
            messagebox.showerror("Erreur", str(exc))
            self.after(100, self.destroy)

    def _update_backend_badge(self) -> None:
        if self._engine is None:
            return
        info = self._engine.backend_info
        style = "Ok.TLabel" if info.exclusive_fullscreen else "Warn.TLabel"
        mark = "✓" if info.exclusive_fullscreen else "⚠"
        self._backend_label.configure(
            text=f"{mark} {info.name}\n{info.detail}",
            style=style,
        )

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        bg, panel, fg, muted, accent = (
            "#0E1116",
            "#161B22",
            "#F2F4F7",
            "#8B949E",
            "#2EE6A6",
        )
        style.configure(".", background=bg, foreground=fg, fieldbackground=panel)
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=fg, font=("Segoe UI", 10))
        style.configure(
            "Title.TLabel", background=bg, foreground=fg, font=("Segoe UI Semibold", 16)
        )
        style.configure(
            "Muted.TLabel", background=bg, foreground=muted, font=("Segoe UI", 9)
        )
        style.configure(
            "Value.TLabel",
            background=bg,
            foreground=accent,
            font=("Segoe UI Semibold", 12),
        )
        style.configure("TButton", background=panel, foreground=fg, padding=8)
        style.map("TButton", background=[("active", "#21262D")])
        style.configure(
            "Accent.TButton",
            background=accent,
            foreground="#0E1116",
            padding=8,
            font=("Segoe UI Semibold", 10),
        )
        style.map("Accent.TButton", background=[("active", "#5EF0C0")])
        style.configure("TCheckbutton", background=bg, foreground=fg)
        style.configure(
            "TCombobox",
            fieldbackground=panel,
            background=panel,
            foreground=fg,
            arrowcolor=fg,
        )
        style.configure(
            "Ok.TLabel", background=bg, foreground=accent, font=("Segoe UI", 9)
        )
        style.configure(
            "Warn.TLabel", background=bg, foreground="#FFB020", font=("Segoe UI", 9)
        )
        style.configure("Horizontal.TScale", background=bg, troughcolor=panel)

    def _build_ui(self) -> None:
        root = ttk.Frame(self)
        root.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)

        ttk.Label(root, text="DebunkPC Color", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            root,
            text="Grading naturel (courbes) — pas le Digital Vibrance plastique.",
            style="Muted.TLabel",
            wraplength=400,
        ).pack(anchor="w", pady=(2, 8))

        self._backend_label = ttk.Label(
            root, text="Backend…", style="Muted.TLabel", wraplength=400
        )
        self._backend_label.pack(anchor="w", pady=(0, 10))

        ttk.Label(root, text="Écran cible").pack(anchor="w")
        self._monitor_var = tk.StringVar()
        self._monitor_combo = ttk.Combobox(
            root, textvariable=self._monitor_var, state="readonly", width=44
        )
        self._monitor_combo.pack(anchor="w", pady=(4, 6))
        ttk.Button(root, text="Rafraîchir écrans", command=self._reload_monitors).pack(
            anchor="w", pady=(0, 8)
        )

        self._all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            root,
            text="Tous les écrans",
            variable=self._all_var,
            command=self._on_all_toggle,
        ).pack(anchor="w")

        ttk.Label(root, text="Preset").pack(anchor="w", pady=(12, 0))
        self._preset_var = tk.StringVar(value="Naturel")
        self._preset_combo = ttk.Combobox(
            root,
            textvariable=self._preset_var,
            state="readonly",
            values=list(PRESETS.keys()) + ["Personnalisé"],
            width=44,
        )
        self._preset_combo.pack(anchor="w", pady=(4, 4))
        self._preset_combo.bind("<<ComboboxSelected>>", self._on_preset)

        ttk.Label(
            root,
            text="Naturel = recommandé. Punch = plus agressif. Vibrance reste basse.",
            style="Muted.TLabel",
            wraplength=400,
        ).pack(anchor="w", pady=(0, 8))

        self._presence = tk.DoubleVar(value=PRESETS["Naturel"].presence * 100)
        self._vibrance = tk.DoubleVar(value=PRESETS["Naturel"].vibrance * 100)
        self._shadow = tk.DoubleVar(value=PRESETS["Naturel"].shadow_lift * 100)
        self._gamma = tk.DoubleVar(value=100)  # mapped around 1.0

        self._add_slider(root, "Présence (contraste naturel)", self._presence, 0, 100)
        self._add_slider(root, "Vibrance (légère)", self._vibrance, 0, 100)
        self._add_slider(root, "Lift ombres (lisibilité)", self._shadow, 0, 40)
        self._add_slider(root, "Gamma (100 = neutre)", self._gamma, 70, 130)

        self._live_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            root, text="Aperçu en direct", variable=self._live_var
        ).pack(anchor="w", pady=(8, 4))

        btns = ttk.Frame(root)
        btns.pack(fill=tk.X, pady=12)
        ttk.Button(btns, text="Réinitialiser", command=self._on_reset).pack(side=tk.LEFT)
        ttk.Button(
            btns, text="Appliquer", style="Accent.TButton", command=self._on_apply
        ).pack(side=tk.RIGHT)

        ttk.Label(
            root,
            text=(
                "Astuce TikTok/jeux : preset Naturel, écran du jeu seulement. "
                "Compatible plein écran exclusif (NVIDIA LUT)."
            ),
            style="Muted.TLabel",
            wraplength=400,
        ).pack(anchor="w")

    def _add_slider(self, parent, label: str, var: tk.DoubleVar, frm: int, to: int) -> None:
        ttk.Label(parent, text=label).pack(anchor="w", pady=(6, 0))
        row = ttk.Frame(parent)
        row.pack(fill=tk.X)
        val = ttk.Label(row, text=f"{int(var.get())}", style="Value.TLabel", width=4)
        val.pack(side=tk.RIGHT)

        def on_move(_=None, v=var, lab=val):
            lab.configure(text=f"{int(round(v.get()))}")
            self._preset_var.set("Personnalisé")
            if self._live_var.get() and self._engine is not None:
                if hasattr(self, "_live_after_id"):
                    self.after_cancel(self._live_after_id)
                self._live_after_id = self.after(90, lambda: self._on_apply(silent=True))

        ttk.Scale(
            row, from_=frm, to=to, orient=tk.HORIZONTAL, variable=var, command=on_move
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

    def _reload_monitors(self) -> None:
        try:
            self._monitors = list_monitors()
        except OSError as exc:
            messagebox.showerror("Erreur", str(exc))
            return
        labels = [m.label for m in self._monitors]
        self._monitor_combo["values"] = labels
        if labels:
            primary = next((i for i, m in enumerate(self._monitors) if m.is_primary), 0)
            self._monitor_combo.current(primary)

    def _selected_monitor(self) -> Monitor | None:
        idx = self._monitor_combo.current()
        if idx < 0 or idx >= len(self._monitors):
            return None
        return self._monitors[idx]

    def _on_all_toggle(self) -> None:
        self._monitor_combo.configure(
            state="disabled" if self._all_var.get() else "readonly"
        )

    def _on_preset(self, _event=None) -> None:
        name = self._preset_var.get()
        if name == "Personnalisé" or name not in PRESETS:
            return
        p = PRESETS[name]
        self._presence.set(p.presence * 100)
        self._vibrance.set(p.vibrance * 100)
        self._shadow.set(p.shadow_lift * 100)
        # gamma 0.7–1.3 ↔ slider 70–130
        self._gamma.set(p.gamma * 100)
        if self._live_var.get():
            self._on_apply(silent=True)

    def _current_params(self) -> GradeParams:
        return GradeParams(
            presence=self._presence.get() / 100.0,
            vibrance=self._vibrance.get() / 100.0,
            shadow_lift=self._shadow.get() / 100.0,
            highlight_roll=0.10,
            gamma=self._gamma.get() / 100.0,
        )

    def _on_apply(self, silent: bool = False) -> None:
        if self._engine is None:
            return
        params = self._current_params()
        # Off / neutre → reset propre
        if (
            params.presence < 0.01
            and params.vibrance < 0.01
            and params.shadow_lift < 0.01
            and abs(params.gamma - 1.0) < 0.02
        ):
            try:
                self._engine.reset()
            except OSError as exc:
                if not silent:
                    messagebox.showerror("Erreur", str(exc))
            return
        try:
            if self._all_var.get():
                self._engine.apply_grade(params, all_monitors=True)
            else:
                mon = self._selected_monitor()
                if mon is None:
                    if not silent:
                        messagebox.showwarning("Écran", "Sélectionne un écran.")
                    return
                self._engine.apply_grade(params, monitor=mon, all_monitors=False)
        except OSError as exc:
            if not silent:
                messagebox.showerror("Erreur", str(exc))

    def _on_reset(self) -> None:
        self._preset_var.set("Off")
        self._on_preset()
        if self._engine:
            try:
                self._engine.reset()
            except OSError as exc:
                messagebox.showerror("Erreur", str(exc))

    def _on_close(self) -> None:
        if self._engine:
            try:
                self._engine.close()
            except Exception:
                pass
        self.destroy()


def run() -> None:
    if sys.platform != "win32":
        print("DebunkPC Color fonctionne uniquement sur Windows.")
        sys.exit(1)
    SaturationApp().mainloop()
