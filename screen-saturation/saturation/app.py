"""Interface Tkinter — sélection d'écran + saturation."""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import messagebox, ttk

from .engine import SaturationEngine
from .matrix import slider_to_saturation
from .monitors import Monitor, list_monitors


class SaturationApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("DebunkPC — Saturation écran")
        self.geometry("420x500")
        self.minsize(380, 460)
        self.configure(bg="#0E1116")

        self._engine: SaturationEngine | None = None
        self._monitors: list[Monitor] = []

        self._build_style()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        try:
            self._engine = SaturationEngine()
            self._reload_monitors()
            self._live_var.set(True)
        except OSError as exc:
            messagebox.showerror("Erreur", str(exc))
            self.after(100, self.destroy)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        bg = "#0E1116"
        panel = "#161B22"
        fg = "#F2F4F7"
        muted = "#8B949E"
        accent = "#2EE6A6"

        style.configure(".", background=bg, foreground=fg, fieldbackground=panel)
        style.configure("TFrame", background=bg)
        style.configure("Card.TFrame", background=panel)
        style.configure("TLabel", background=bg, foreground=fg, font=("Segoe UI", 10))
        style.configure(
            "Title.TLabel",
            background=bg,
            foreground=fg,
            font=("Segoe UI Semibold", 16),
        )
        style.configure(
            "Muted.TLabel",
            background=bg,
            foreground=muted,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Value.TLabel",
            background=bg,
            foreground=accent,
            font=("Segoe UI Semibold", 14),
        )
        style.configure(
            "TButton",
            background=panel,
            foreground=fg,
            padding=8,
            font=("Segoe UI", 10),
        )
        style.map("TButton", background=[("active", "#21262D")])
        style.configure(
            "Accent.TButton",
            background=accent,
            foreground="#0E1116",
            padding=8,
            font=("Segoe UI Semibold", 10),
        )
        style.map("Accent.TButton", background=[("active", "#5EF0C0")])
        style.configure(
            "TCheckbutton",
            background=bg,
            foreground=fg,
            font=("Segoe UI", 10),
        )
        style.configure(
            "TCombobox",
            fieldbackground=panel,
            background=panel,
            foreground=fg,
            arrowcolor=fg,
        )
        style.configure(
            "Horizontal.TScale",
            background=bg,
            troughcolor=panel,
        )

    def _build_ui(self) -> None:
        pad = {"padx": 20, "pady": 6}
        root = ttk.Frame(self, style="TFrame")
        root.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        ttk.Label(root, text="DebunkPC", style="Title.TLabel").pack(
            anchor="w", **pad
        )
        ttk.Label(
            root,
            text="Saturation des couleurs par écran — preuves visuelles, pas de magie GPU.",
            style="Muted.TLabel",
            wraplength=360,
        ).pack(anchor="w", padx=20, pady=(0, 12))

        ttk.Label(root, text="Écran cible").pack(anchor="w", padx=20)
        self._monitor_var = tk.StringVar()
        self._monitor_combo = ttk.Combobox(
            root,
            textvariable=self._monitor_var,
            state="readonly",
            width=42,
        )
        self._monitor_combo.pack(anchor="w", padx=20, pady=(4, 8))

        row = ttk.Frame(root)
        row.pack(fill=tk.X, padx=20, pady=(0, 8))
        ttk.Button(row, text="Rafraîchir écrans", command=self._reload_monitors).pack(
            side=tk.LEFT
        )

        self._all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            root,
            text="Appliquer à tous les écrans",
            variable=self._all_var,
            command=self._on_all_toggle,
        ).pack(anchor="w", padx=20, pady=8)

        ttk.Label(root, text="Saturation").pack(anchor="w", padx=20, pady=(8, 0))
        self._value_label = ttk.Label(root, text="100 % (normal)", style="Value.TLabel")
        self._value_label.pack(anchor="w", padx=20, pady=(2, 4))

        self._sat_var = tk.DoubleVar(value=100.0)
        self._live_var = tk.BooleanVar(value=False)
        self._scale = ttk.Scale(
            root,
            from_=0,
            to=200,
            orient=tk.HORIZONTAL,
            variable=self._sat_var,
            command=self._on_slider,
        )
        self._scale.pack(fill=tk.X, padx=20, pady=4)

        hints = ttk.Frame(root)
        hints.pack(fill=tk.X, padx=20)
        ttk.Label(hints, text="0 % gris", style="Muted.TLabel").pack(side=tk.LEFT)
        ttk.Label(hints, text="200 % max", style="Muted.TLabel").pack(side=tk.RIGHT)

        ttk.Checkbutton(
            root,
            text="Aperçu en direct (applique en bougeant le slider)",
            variable=self._live_var,
        ).pack(anchor="w", padx=20, pady=(0, 8))

        btns = ttk.Frame(root)
        btns.pack(fill=tk.X, padx=20, pady=18)
        ttk.Button(
            btns, text="Réinitialiser", command=self._on_reset
        ).pack(side=tk.LEFT)
        ttk.Button(
            btns,
            text="Appliquer",
            style="Accent.TButton",
            command=self._on_apply,
        ).pack(side=tk.RIGHT)

        ttk.Label(
            root,
            text=(
                "Astuce jeux : mode bordless / fenêtré recommandé. "
                "Le plein écran exclusif peut ignorer le filtre."
            ),
            style="Muted.TLabel",
            wraplength=360,
        ).pack(anchor="w", padx=20, pady=(4, 8))

    def _reload_monitors(self) -> None:
        try:
            self._monitors = list_monitors()
        except OSError as exc:
            messagebox.showerror("Erreur", str(exc))
            return

        labels = [m.label for m in self._monitors]
        self._monitor_combo["values"] = labels
        if labels:
            # Préférer l'écran principal
            primary = next((i for i, m in enumerate(self._monitors) if m.is_primary), 0)
            self._monitor_combo.current(primary)

    def _selected_monitor(self) -> Monitor | None:
        idx = self._monitor_combo.current()
        if idx < 0 or idx >= len(self._monitors):
            return None
        return self._monitors[idx]

    def _on_all_toggle(self) -> None:
        state = "disabled" if self._all_var.get() else "readonly"
        self._monitor_combo.configure(state=state)

    def _on_slider(self, _value: str | None = None) -> None:
        pct = int(round(float(self._sat_var.get())))
        if pct == 100:
            text = "100 % (normal)"
        elif pct == 0:
            text = "0 % (niveaux de gris)"
        elif pct > 100:
            text = f"{pct} % (plus saturé)"
        else:
            text = f"{pct} % (moins saturé)"
        self._value_label.configure(text=text)
        if self._live_var.get() and self._engine is not None:
            # Debounce léger via after — évite de spammer l'API
            if hasattr(self, "_live_after_id"):
                self.after_cancel(self._live_after_id)
            self._live_after_id = self.after(80, lambda: self._on_apply(silent=True))

    def _on_apply(self, silent: bool = False) -> None:
        if self._engine is None:
            return
        sat = slider_to_saturation(self._sat_var.get())
        try:
            # À 100 %, on retire complètement le filtre (plus propre pour les jeux)
            if abs(sat - 1.0) < 1e-6:
                self._engine.reset()
                return
            if self._all_var.get():
                self._engine.apply(sat, all_monitors=True)
            else:
                monitor = self._selected_monitor()
                if monitor is None:
                    if not silent:
                        messagebox.showwarning("Écran", "Sélectionne un écran.")
                    return
                self._engine.apply(sat, monitor=monitor, all_monitors=False)
        except OSError as exc:
            if not silent:
                messagebox.showerror("Erreur", str(exc))

    def _on_reset(self) -> None:
        if self._engine is None:
            return
        self._sat_var.set(100)
        self._on_slider()
        try:
            self._engine.reset()
        except OSError as exc:
            messagebox.showerror("Erreur", str(exc))

    def _on_close(self) -> None:
        if self._engine is not None:
            try:
                self._engine.close()
            except Exception:
                pass
        self.destroy()


def run() -> None:
    if sys.platform != "win32":
        print("DebunkPC Saturation fonctionne uniquement sur Windows.")
        sys.exit(1)
    app = SaturationApp()
    app.mainloop()
