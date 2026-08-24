from __future__ import annotations

import copy
import sys
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import pyautogui
from pynput import keyboard

from engine import Action, AutomationRunner, RunSettings, load_profile, save_profile

APP_NAME = "KeyClick Automator"
APP_VERSION = "2.1.0"

# A calm, light, system-native palette inspired by modern productivity apps.
BG = "#F4F5F7"
SIDEBAR = "#ECEEF2"
PANEL = "#FFFFFF"
PANEL_2 = "#E8EAF0"
BORDER = "#CDD1D8"
BORDER_ACTIVE = "#007AFF"
TEXT = "#15161A"
MUTED = "#50535B"
SUBTLE = "#747780"
ACCENT = "#007AFF"
ACCENT_HOVER = "#0066D6"
DANGER = "#D70015"
SUCCESS = "#248A3D"
FONT = "Segoe UI"
FONT_DISPLAY = "Segoe UI"

ACTION_NAMES = {
    "Key press": "key",
    "Hotkey": "hotkey",
    "Type text": "text",
    "Left click": "left_click",
    "Right click": "right_click",
    "Double click": "double_click",
    "Middle click": "middle_click",
    "Scroll": "scroll",
    "Drag": "drag",
}
KIND_NAMES = {value: key for key, value in ACTION_NAMES.items()}
MOUSE_KINDS = {"left_click", "right_click", "double_click", "middle_click", "scroll", "drag"}

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.01
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


class AutomatorApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.attributes("-alpha", 0.0)
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1280x800")
        self.minsize(1120, 720)
        self.configure(fg_color=BG)

        self.actions: list[Action] = []
        self.selected_index: int | None = None
        self.editing_index: int | None = None
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.hotkey_listener: keyboard.Listener | None = None
        self.capture_target = "start"
        self.key_capture_listener: keyboard.Listener | None = None
        self._status_color = MUTED
        self._status_target = MUTED
        self._status_animation_generation = 0

        self._make_variables()
        self._build_layout()
        self._bind_events()
        self._start_global_hotkeys()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._render_actions()
        self._show_inspector("Action")
        self.after(40, self._animate_window_in)

    def _make_variables(self) -> None:
        self.action_type = ctk.StringVar(value="Key press")
        self.action_value = ctk.StringVar(value="space")
        self.x_var = ctk.StringVar(value="0")
        self.y_var = ctk.StringVar(value="0")
        self.x2_var = ctk.StringVar(value="0")
        self.y2_var = ctk.StringVar(value="0")
        self.amount_var = ctk.StringVar(value="-3")
        self.duration_var = ctk.StringVar(value="0.4")
        self.action_repeats_var = ctk.StringVar(value="1")
        self.action_delay = ctk.StringVar(value="0.10")
        self.repeat_var = ctk.StringVar(value="1")
        self.start_delay_var = ctk.StringVar(value="3.0")
        self.cycle_interval_var = ctk.StringVar(value="0.0")
        self.text_interval_var = ctk.StringVar(value="0.02")
        self.jitter_var = ctk.StringVar(value="0.0")
        self.repeat_forever_var = ctk.BooleanVar(value=False)
        self.start_hotkey_var = ctk.StringVar(value="f6")
        self.capture_hotkey_var = ctk.StringVar(value="f8")
        self.stop_hotkey_var = ctk.StringVar(value="f9")
        self.always_on_top_var = ctk.BooleanVar(value=False)
        self.status_var = ctk.StringVar(value="Ready")
        self.summary_var = ctk.StringVar(value="No actions yet")
        self.inspector_tab_var = ctk.StringVar(value="Action")

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, minsize=220)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, minsize=360)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_workspace()
        self._build_inspector()

    def _animate_window_in(self, step: int = 0) -> None:
        """Short native-feeling entrance; never blocks interaction."""
        frames = 9
        try:
            progress = min(1.0, step / frames)
            eased = 1 - (1 - progress) ** 3
            self.attributes("-alpha", eased)
            if step < frames:
                self.after(18, lambda: self._animate_window_in(step + 1))
        except Exception:
            self.attributes("-alpha", 1.0)

    @staticmethod
    def _mix_color(start: str, end: str, amount: float) -> str:
        a = tuple(int(start[i:i + 2], 16) for i in (1, 3, 5))
        b = tuple(int(end[i:i + 2], 16) for i in (1, 3, 5))
        rgb = tuple(round(x + (y - x) * amount) for x, y in zip(a, b))
        return "#" + "".join(f"{value:02X}" for value in rgb)

    def _animate_status_color(self, target: str, generation: int, step: int = 0, start: str | None = None) -> None:
        if generation != self._status_animation_generation:
            return
        start = start or self._status_color
        frames = 7
        amount = min(1.0, step / frames)
        eased = 1 - (1 - amount) ** 2
        try:
            self.status_badge.configure(text_color=self._mix_color(start, target, eased))
            if step < frames:
                self.after(22, lambda: self._animate_status_color(target, generation, step + 1, start))
            else:
                self._status_color = target
        except Exception:
            self._status_color = target

    def _animate_empty_icon(self, widget, step: int = 0) -> None:
        colors = ["#F0F6FF", "#E8F2FF", "#DDEBFF", "#D4E6FF", "#DDEBFF", "#E8F2FF"]
        try:
            if widget.winfo_exists() and step < len(colors):
                widget.configure(fg_color=colors[step])
                self.after(55, lambda: self._animate_empty_icon(widget, step + 1))
        except Exception:
            return

    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=SIDEBAR, border_width=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(8, weight=1)

        mark = ctk.CTkFrame(sidebar, width=42, height=42, corner_radius=12, fg_color=ACCENT)
        mark.grid(row=0, column=0, padx=20, pady=(24, 0), sticky="w")
        mark.grid_propagate(False)
        ctk.CTkLabel(mark, text="K", font=ctk.CTkFont(FONT, 19, "bold"), text_color="#FFFFFF").place(relx=.5, rely=.5, anchor="center")
        ctk.CTkLabel(sidebar, text="KeyClick", font=ctk.CTkFont(FONT_DISPLAY, 19, "bold"), text_color=TEXT).grid(row=1, column=0, padx=20, pady=(11, 0), sticky="w")
        ctk.CTkLabel(sidebar, text=f"AUTOMATOR  ·  {APP_VERSION}", font=ctk.CTkFont(FONT, 12, "bold"), text_color=SUBTLE).grid(row=2, column=0, padx=20, pady=(1, 26), sticky="w")

        self._sidebar_label(sidebar, "PROFILE", 3)
        self._sidebar_button(sidebar, "Open profile", self.load_profile_dialog, 4)
        self._sidebar_button(sidebar, "Save profile", self.save_profile_dialog, 5)
        self._sidebar_button(sidebar, "New sequence", self.clear_all, 6)

        divider = ctk.CTkFrame(sidebar, height=1, fg_color=BORDER)
        divider.grid(row=7, column=0, padx=18, pady=18, sticky="ew")

        safety = ctk.CTkFrame(sidebar, fg_color="#F8F9FB", corner_radius=16, border_width=0)
        safety.grid(row=9, column=0, padx=14, pady=(0, 16), sticky="sew")
        ctk.CTkLabel(safety, text="GLOBAL CONTROLS", font=ctk.CTkFont(FONT, 11, "bold"), text_color=SUBTLE).pack(anchor="w", padx=13, pady=(12, 8))
        self._shortcut_row(safety, self.start_hotkey_var, "Start")
        self._shortcut_row(safety, self.capture_hotkey_var, "Capture")
        self._shortcut_row(safety, self.stop_hotkey_var, "Stop")
        ctk.CTkLabel(safety, text="Move the cursor to a screen\ncorner for an emergency stop.", justify="left", font=ctk.CTkFont(FONT, 11), text_color=MUTED).pack(anchor="w", padx=13, pady=(8, 12))

    def _sidebar_label(self, parent, text: str, row: int) -> None:
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(FONT, 11, "bold"), text_color=SUBTLE).grid(row=row, column=0, padx=18, pady=(0, 7), sticky="w")

    def _sidebar_button(self, parent, text: str, command, row: int) -> None:
        ctk.CTkButton(parent, text=text, command=command, height=40, corner_radius=10, fg_color="transparent", hover_color="#DDE1E8", border_width=0, anchor="w", font=ctk.CTkFont(FONT, 13, "bold"), text_color=TEXT).grid(row=row, column=0, padx=10, pady=2, sticky="ew")

    def _shortcut_row(self, parent, key_var, label: str) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=13, pady=2)
        ctk.CTkLabel(row, textvariable=key_var, width=52, height=22, corner_radius=5, fg_color=PANEL_2, font=ctk.CTkFont("Consolas", 9, "bold"), text_color=TEXT).pack(side="left")
        ctk.CTkLabel(row, text=label, font=ctk.CTkFont(FONT, 12), text_color=MUTED).pack(side="left", padx=8)

    def _build_workspace(self) -> None:
        workspace = ctk.CTkFrame(self, corner_radius=0, fg_color=BG)
        workspace.grid(row=0, column=1, sticky="nsew")
        workspace.grid_columnconfigure(0, weight=1)
        workspace.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(workspace, fg_color="transparent")
        header.grid(row=0, column=0, padx=28, pady=(24, 0), sticky="ew")
        ctk.CTkLabel(header, text="Sequence builder", font=ctk.CTkFont(FONT_DISPLAY, 30, "bold"), text_color=TEXT).pack(side="left")
        self.status_badge = ctk.CTkLabel(header, textvariable=self.status_var, height=32, corner_radius=10, fg_color=PANEL_2, font=ctk.CTkFont(FONT, 12, "bold"), text_color=MUTED)
        self.status_badge.pack(side="right")

        ctk.CTkLabel(workspace, text="Build keyboard and mouse routines with clear timing, order, and safety controls.", font=ctk.CTkFont(FONT, 13), text_color=MUTED).grid(row=1, column=0, padx=28, pady=(2, 16), sticky="w")

        toolbar = ctk.CTkFrame(workspace, height=48, corner_radius=12, fg_color=PANEL, border_width=0)
        toolbar.grid(row=2, column=0, padx=28, pady=(0, 12), sticky="ew")
        toolbar.grid_propagate(False)
        self.summary_label = ctk.CTkLabel(toolbar, textvariable=self.summary_var, font=ctk.CTkFont(FONT, 12, "bold"), text_color=MUTED)
        self.summary_label.pack(side="left", padx=13)
        for text, command in [("Delete", self.delete_selected), ("Duplicate", self.duplicate_selected), ("Move down", lambda: self.move_selected(1)), ("Move up", lambda: self.move_selected(-1))]:
            ctk.CTkButton(toolbar, text=text, command=command, width=80, height=34, corner_radius=9, fg_color="transparent", hover_color=PANEL_2, text_color=TEXT, font=ctk.CTkFont(FONT, 12, "bold")).pack(side="right", padx=(0, 4))

        self.action_list = ctk.CTkScrollableFrame(workspace, corner_radius=16, fg_color=PANEL, border_width=0, scrollbar_button_color="#B9BEC7", scrollbar_button_hover_color="#969DA8")
        self.action_list.grid(row=3, column=0, padx=28, pady=(0, 12), sticky="nsew")
        self.action_list.grid_columnconfigure(0, weight=1)

        runbar = ctk.CTkFrame(workspace, height=76, corner_radius=16, fg_color=PANEL, border_width=0)
        runbar.grid(row=4, column=0, padx=28, pady=(0, 22), sticky="ew")
        runbar.grid_propagate(False)
        runbar.grid_columnconfigure(0, weight=1)
        info = ctk.CTkFrame(runbar, fg_color="transparent")
        info.grid(row=0, column=0, padx=14, pady=10, sticky="ew")
        ctk.CTkLabel(info, text="RUN STATUS", font=ctk.CTkFont(FONT, 10, "bold"), text_color=SUBTLE).pack(anchor="w")
        self.run_status_label = ctk.CTkLabel(info, text="Waiting for a sequence", font=ctk.CTkFont(FONT, 13), text_color=MUTED)
        self.run_status_label.pack(anchor="w")
        self.progress = ctk.CTkProgressBar(runbar, width=120, height=7, corner_radius=4, fg_color=PANEL_2, progress_color=ACCENT)
        self.progress.grid(row=0, column=1, padx=10)
        self.progress.set(0)
        self.stop_button = ctk.CTkButton(runbar, text="Stop", command=self.stop_run, width=82, height=44, corner_radius=12, fg_color="#FDECEE", hover_color="#F9DDE1", text_color=DANGER, font=ctk.CTkFont(FONT, 13, "bold"), state="disabled")
        self.stop_button.grid(row=0, column=2, padx=(0, 8))
        self.start_button = ctk.CTkButton(runbar, text="Start  F6", command=self.start_run, width=116, height=44, corner_radius=12, fg_color=ACCENT, hover_color=ACCENT_HOVER, font=ctk.CTkFont(FONT, 13, "bold"))
        self.start_button.grid(row=0, column=3, padx=(0, 12))

    def _build_inspector(self) -> None:
        inspector = ctk.CTkFrame(self, width=360, corner_radius=0, fg_color=PANEL, border_width=0)
        inspector.grid(row=0, column=2, sticky="nsew")
        inspector.grid_propagate(False)
        inspector.grid_columnconfigure(0, weight=1)
        inspector.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(inspector, text="Inspector", font=ctk.CTkFont(FONT_DISPLAY, 21, "bold"), text_color=TEXT).grid(row=0, column=0, padx=22, pady=(24, 12), sticky="w")
        self.tab_control = ctk.CTkSegmentedButton(inspector, values=["Action", "Run"], variable=self.inspector_tab_var, command=self._show_inspector, height=40, corner_radius=10, fg_color="#F2F3F6", selected_color="#DDE7F5", selected_hover_color="#D4E1F3", unselected_color="#F2F3F6", unselected_hover_color="#E8EAF0", text_color=TEXT, font=ctk.CTkFont(FONT, 12, "bold"))
        self.tab_control.grid(row=1, column=0, padx=22, pady=(0, 14), sticky="ew")

        self.inspector_stack = ctk.CTkFrame(inspector, fg_color="transparent")
        self.inspector_stack.grid(row=2, column=0, sticky="nsew")
        self.inspector_stack.grid_columnconfigure(0, weight=1)
        self.inspector_stack.grid_rowconfigure(0, weight=1)
        self.action_panel = ctk.CTkScrollableFrame(self.inspector_stack, corner_radius=0, fg_color="transparent", scrollbar_button_color="#C7C7CC")
        self.run_panel = ctk.CTkScrollableFrame(self.inspector_stack, corner_radius=0, fg_color="transparent", scrollbar_button_color="#C7C7CC")
        self._build_action_form()
        self._build_run_form()

    def _form_label(self, parent, text: str) -> None:
        ctk.CTkLabel(parent, text=text.upper(), font=ctk.CTkFont(FONT, 10, "bold"), text_color=SUBTLE).pack(anchor="w", pady=(14, 6))

    def _entry(self, parent, variable, placeholder: str = ""):
        return ctk.CTkEntry(parent, textvariable=variable, height=42, corner_radius=10, fg_color="#FAFBFC", border_color=BORDER, border_width=1, text_color=TEXT, placeholder_text=placeholder, placeholder_text_color=SUBTLE, font=ctk.CTkFont(FONT, 13))

    def _build_action_form(self) -> None:
        p = self.action_panel
        self.form_sections: dict[str, ctk.CTkFrame] = {}
        top = ctk.CTkFrame(p, fg_color="transparent")
        top.pack(fill="x", padx=6)
        ctk.CTkButton(top, text="＋  New action", command=self.new_action, height=40, corner_radius=10, fg_color="#EFF1F5", hover_color="#E3E6EC", text_color=TEXT, font=ctk.CTkFont(FONT, 13, "bold")).pack(fill="x", pady=(0, 4))

        self._form_label(p, "Action type")
        self.action_combo = ctk.CTkComboBox(p, values=list(ACTION_NAMES), variable=self.action_type, command=lambda _: self._update_action_fields(), height=42, corner_radius=10, fg_color="#FAFBFC", border_color=BORDER, button_color=PANEL_2, button_hover_color="#DDE1E8", dropdown_fg_color=PANEL, dropdown_hover_color="#E8F2FF", text_color=TEXT, font=ctk.CTkFont(FONT, 13))
        self.action_combo.pack(fill="x", padx=6)

        value = ctk.CTkFrame(p, fg_color="transparent")
        self.form_sections["value"] = value
        self._form_label(value, "Key, hotkey, or text")
        self.value_entry = self._entry(value, self.action_value, "space / ctrl+s / your text")
        self.value_entry.pack(fill="x")
        self.record_key_button = ctk.CTkButton(value, text="⌨  Record key press", command=self._record_action_key, height=38, corner_radius=10, fg_color=PANEL_2, hover_color="#DDE1E8", text_color=TEXT, font=ctk.CTkFont(FONT, 12, "bold"))
        self.record_key_button.pack(fill="x", pady=(6, 0))
        value.pack(fill="x", padx=6)

        start = ctk.CTkFrame(p, fg_color="transparent")
        self.form_sections["start"] = start
        self._form_label(start, "Screen position")
        coords = ctk.CTkFrame(start, fg_color="transparent")
        coords.pack(fill="x")
        self._entry(coords, self.x_var).pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._entry(coords, self.y_var).pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.capture_position_button = ctk.CTkButton(start, text="Capture cursor position  F8", command=lambda: self.record_position_countdown("start"), height=38, corner_radius=10, fg_color=PANEL_2, hover_color="#DDE1E8", text_color=TEXT, font=ctk.CTkFont(FONT, 12, "bold"))
        self.capture_position_button.pack(fill="x", pady=(6, 0))

        dest = ctk.CTkFrame(p, fg_color="transparent")
        self.form_sections["dest"] = dest
        self._form_label(dest, "Drag destination")
        dest_coords = ctk.CTkFrame(dest, fg_color="transparent")
        dest_coords.pack(fill="x")
        self._entry(dest_coords, self.x2_var).pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._entry(dest_coords, self.y2_var).pack(side="left", fill="x", expand=True, padx=(4, 0))
        ctk.CTkButton(dest, text="Capture destination", command=lambda: self.record_position_countdown("dest"), height=30, corner_radius=7, fg_color=PANEL_2, hover_color="#E5E5EA", text_color=MUTED, font=ctk.CTkFont(FONT, 11, "bold")).pack(fill="x", pady=(6, 0))

        scroll = ctk.CTkFrame(p, fg_color="transparent")
        self.form_sections["scroll"] = scroll
        self._form_label(scroll, "Scroll amount")
        self._entry(scroll, self.amount_var, "-3 down / 3 up").pack(fill="x")

        duration = ctk.CTkFrame(p, fg_color="transparent")
        self.form_sections["duration"] = duration
        self._form_label(duration, "Drag duration (seconds)")
        self._entry(duration, self.duration_var).pack(fill="x")

        timing = ctk.CTkFrame(p, fg_color="transparent")
        self.timing_frame = timing
        timing.pack(fill="x", padx=6)
        self._form_label(timing, "Action behavior")
        timing_row = ctk.CTkFrame(timing, fg_color="transparent")
        timing_row.pack(fill="x")
        left = ctk.CTkFrame(timing_row, fg_color="transparent")
        right = ctk.CTkFrame(timing_row, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True, padx=(0, 4))
        right.pack(side="left", fill="x", expand=True, padx=(4, 0))
        ctk.CTkLabel(left, text="REPEATS", font=ctk.CTkFont(FONT, 10, "bold"), text_color=SUBTLE).pack(anchor="w", pady=(0, 4))
        self._entry(left, self.action_repeats_var).pack(fill="x")
        ctk.CTkLabel(right, text="WAIT AFTER", font=ctk.CTkFont(FONT, 10, "bold"), text_color=SUBTLE).pack(anchor="w", pady=(0, 4))
        self._entry(right, self.action_delay).pack(fill="x")

        self.add_button = ctk.CTkButton(p, text="Add to sequence", command=self.add_or_update_action, height=48, corner_radius=12, fg_color=ACCENT, hover_color=ACCENT_HOVER, font=ctk.CTkFont(FONT, 14, "bold"))
        self.add_button.pack(fill="x", padx=6, pady=(20, 18))
        self._update_action_fields()

    def _build_run_form(self) -> None:
        p = self.run_panel
        ctk.CTkLabel(p, text="RUN PLAN", font=ctk.CTkFont(FONT, 11, "bold"), text_color=SUBTLE).pack(anchor="w", padx=6, pady=(2, 6))
        ctk.CTkLabel(p, text="Choose when it stops", font=ctk.CTkFont(FONT_DISPLAY, 17, "bold"), text_color=TEXT).pack(anchor="w", padx=6)
        ctk.CTkLabel(p, text="Run a fixed number of cycles or continue until you press Stop.", wraplength=270, justify="left", font=ctk.CTkFont(FONT, 12), text_color=MUTED).pack(anchor="w", padx=6, pady=(1, 10))

        forever_row = ctk.CTkFrame(p, fg_color=PANEL, corner_radius=10, border_width=1, border_color=BORDER)
        forever_row.pack(fill="x", padx=6, pady=(0, 2))
        ctk.CTkLabel(forever_row, text="Loop indefinitely", font=ctk.CTkFont(FONT, 12, "bold"), text_color=TEXT).pack(side="left", padx=11, pady=10)
        ctk.CTkSwitch(forever_row, text="", variable=self.repeat_forever_var, command=self._toggle_repeat_mode, width=38, progress_color=ACCENT, button_color="#FFFFFF", button_hover_color="#FFFFFF").pack(side="right", padx=9)

        self._form_label(p, "Repeat cycles")
        self.repeat_entry = self._entry(p, self.repeat_var)
        self.repeat_entry.pack(fill="x", padx=6)
        ctk.CTkLabel(p, text="Whole sequence repetitions", font=ctk.CTkFont(FONT, 10), text_color=SUBTLE).pack(anchor="w", padx=7, pady=(2, 0))

        for label, variable, hint in [
            ("Start countdown", self.start_delay_var, "Seconds before the first action"),
            ("Between cycles", self.cycle_interval_var, "Pause after each sequence"),
            ("Typing interval", self.text_interval_var, "Seconds between characters"),
            ("Timing variation ±", self.jitter_var, "Optional variation added to waits"),
        ]:
            self._form_label(p, label)
            self._entry(p, variable).pack(fill="x", padx=6)
            ctk.CTkLabel(p, text=hint, font=ctk.CTkFont(FONT, 10), text_color=SUBTLE).pack(anchor="w", padx=7, pady=(2, 0))

        divider = ctk.CTkFrame(p, height=1, fg_color=BORDER)
        divider.pack(fill="x", padx=6, pady=14)
        self._form_label(p, "Global shortcuts")
        ctk.CTkLabel(p, text="Use a key or combination such as f6 or ctrl+shift+s.", wraplength=270, justify="left", font=ctk.CTkFont(FONT, 11), text_color=MUTED).pack(anchor="w", padx=6, pady=(0, 5))
        for label, variable in [
            ("Start / toggle", self.start_hotkey_var),
            ("Capture position", self.capture_hotkey_var),
            ("Emergency stop", self.stop_hotkey_var),
        ]:
            row = ctk.CTkFrame(p, fg_color="transparent")
            row.pack(fill="x", padx=6, pady=3)
            ctk.CTkLabel(row, text=label, width=112, anchor="w", font=ctk.CTkFont(FONT, 11), text_color=MUTED).pack(side="left")
            self._entry(row, variable).pack(side="right", fill="x", expand=True)
        ctk.CTkButton(p, text="Apply shortcuts", command=self._apply_hotkeys, height=32, corner_radius=8, fg_color=PANEL_2, hover_color="#E5E5EA", text_color=TEXT, font=ctk.CTkFont(FONT, 11, "bold")).pack(fill="x", padx=6, pady=(6, 0))

        divider = ctk.CTkFrame(p, height=1, fg_color=BORDER)
        divider.pack(fill="x", padx=6, pady=14)
        top_row = ctk.CTkFrame(p, fg_color="transparent")
        top_row.pack(fill="x", padx=6)
        ctk.CTkLabel(top_row, text="Keep window on top", font=ctk.CTkFont(FONT, 12), text_color=MUTED).pack(side="left")
        ctk.CTkSwitch(top_row, text="", variable=self.always_on_top_var, command=self._toggle_always_on_top, width=38, progress_color=ACCENT, button_color=TEXT, button_hover_color="#FFFFFF").pack(side="right")

        self.run_summary = ctk.CTkFrame(p, corner_radius=10, fg_color=PANEL, border_width=1, border_color=BORDER)
        self.run_summary.pack(fill="x", padx=6, pady=(15, 16))
        ctk.CTkLabel(self.run_summary, text="SEQUENCE OVERVIEW", font=ctk.CTkFont(FONT, 10, "bold"), text_color=SUBTLE).pack(anchor="w", padx=12, pady=(11, 4))
        self.run_summary_label = ctk.CTkLabel(self.run_summary, text="0 active actions", justify="left", font=ctk.CTkFont(FONT, 13, "bold"), text_color=TEXT)
        self.run_summary_label.pack(anchor="w", padx=12)
        self.operation_summary_label = ctk.CTkLabel(self.run_summary, text="0 operations per run", justify="left", font=ctk.CTkFont(FONT, 11), text_color=MUTED)
        self.operation_summary_label.pack(anchor="w", padx=12, pady=(1, 11))

    def _show_inspector(self, name: str) -> None:
        self.action_panel.grid_forget()
        self.run_panel.grid_forget()
        if name == "Run":
            self._update_summary()
            self.run_panel.grid(row=0, column=0, sticky="nsew")
        else:
            self.action_panel.grid(row=0, column=0, sticky="nsew")

    def _bind_events(self) -> None:
        self.bind("<Control-s>", lambda _e: self.save_profile_dialog())
        self.bind("<Control-o>", lambda _e: self.load_profile_dialog())

    def _update_action_fields(self) -> None:
        kind = ACTION_NAMES.get(self.action_type.get(), "key")
        for section in self.form_sections.values():
            section.pack_forget()
        if kind not in MOUSE_KINDS:
            self.form_sections["value"].pack(fill="x", padx=6, before=self.timing_frame)
            if kind == "text":
                self.record_key_button.pack_forget()
            elif not self.record_key_button.winfo_manager():
                self.record_key_button.pack(fill="x", pady=(6, 0))
        else:
            self.form_sections["start"].pack(fill="x", padx=6, before=self.timing_frame)
        if kind == "drag":
            self.form_sections["dest"].pack(fill="x", padx=6, before=self.timing_frame)
            self.form_sections["duration"].pack(fill="x", padx=6, before=self.timing_frame)
        if kind == "scroll":
            self.form_sections["scroll"].pack(fill="x", padx=6, before=self.timing_frame)

    def _action_from_form(self) -> Action:
        kind = ACTION_NAMES[self.action_type.get()]
        try:
            mouse = kind in MOUSE_KINDS
            action = Action(
                kind=kind,
                value=self.action_value.get(),
                x=int(self.x_var.get()) if mouse else None,
                y=int(self.y_var.get()) if mouse else None,
                x2=int(self.x2_var.get()) if kind == "drag" else None,
                y2=int(self.y2_var.get()) if kind == "drag" else None,
                amount=int(self.amount_var.get()) if kind == "scroll" else 0,
                duration=float(self.duration_var.get()) if kind == "drag" else 0.4,
                repeats=int(self.action_repeats_var.get()),
                delay_after=float(self.action_delay.get()),
            )
        except ValueError as exc:
            raise ValueError("Coordinates, repeats, amount, duration, and wait values must be valid numbers.") from exc
        action.validate(self._reserved_key_parts())
        return action

    def _record_action_key(self) -> None:
        if self.key_capture_listener:
            self.key_capture_listener.stop()
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        self.record_key_button.configure(text="Press any key…", fg_color="#E8F2FF", text_color=ACCENT)
        self._set_status("Listening for a key", ACCENT)

        def on_press(key) -> bool:
            if isinstance(key, keyboard.KeyCode):
                name = key.char
            else:
                name = getattr(key, "name", None)
            if name:
                self.after(0, lambda value=name: self._finish_key_capture(value))
            return False

        self.key_capture_listener = keyboard.Listener(on_press=on_press)
        self.key_capture_listener.daemon = True
        self.key_capture_listener.start()

    def _finish_key_capture(self, value: str) -> None:
        self.action_value.set(value.lower())
        self.record_key_button.configure(text="⌨  Record key press", fg_color=PANEL_2, text_color=TEXT)
        self._set_status(f"Recorded {value.upper()}", SUCCESS)
        self.key_capture_listener = None
        self._start_global_hotkeys()

    def new_action(self) -> None:
        self.editing_index = None
        self.selected_index = None
        self.add_button.configure(text="Add to sequence")
        self.action_type.set("Key press")
        self.action_value.set("space")
        self.action_repeats_var.set("1")
        self.action_delay.set("0.10")
        self._update_action_fields()
        self._render_actions()

    def add_or_update_action(self) -> None:
        try:
            action = self._action_from_form()
            if self.editing_index is None:
                self.actions.append(action)
                self.selected_index = len(self.actions) - 1
                self._set_status("Action added", SUCCESS)
            else:
                action.enabled = self.actions[self.editing_index].enabled
                self.actions[self.editing_index] = action
                self.selected_index = self.editing_index
                self._set_status("Action updated", SUCCESS)
            self.editing_index = None
            self.add_button.configure(text="Add to sequence")
            self._render_actions()
        except ValueError as exc:
            messagebox.showerror("Check this action", str(exc), parent=self)

    def _target_text(self, action: Action) -> str:
        if action.kind == "drag":
            return f"{action.x}, {action.y}  →  {action.x2}, {action.y2}"
        if action.kind == "scroll":
            direction = "up" if action.amount > 0 else "down"
            return f"{abs(action.amount)} ticks {direction} at {action.x}, {action.y}"
        if action.kind in MOUSE_KINDS:
            return f"Screen position {action.x}, {action.y}"
        text = action.value.replace("\n", " ↵ ")
        return text if len(text) <= 54 else text[:51] + "..."

    def _render_actions(self) -> None:
        for child in self.action_list.winfo_children():
            child.destroy()
        if not self.actions:
            empty = ctk.CTkFrame(self.action_list, height=270, corner_radius=14, fg_color="transparent")
            empty.grid(row=0, column=0, sticky="ew", padx=14, pady=24)
            empty.grid_propagate(False)
            content = ctk.CTkFrame(empty, fg_color="transparent")
            content.place(relx=.5, rely=.5, anchor="center")
            plus = ctk.CTkLabel(content, text="＋", width=54, height=54, corner_radius=17, fg_color="#E8F2FF", text_color=ACCENT, font=ctk.CTkFont(FONT, 28, "bold"))
            plus.pack(pady=(0, 16))
            self.after(120, lambda: self._animate_empty_icon(plus))
            ctk.CTkLabel(content, text="Build your first sequence", font=ctk.CTkFont(FONT_DISPLAY, 21, "bold"), text_color=TEXT).pack()
            ctk.CTkLabel(content, text="Add a key press, click, scroll, or text action to get started.", font=ctk.CTkFont(FONT, 13), text_color=MUTED).pack(pady=(6, 16))
            ctk.CTkButton(content, text="Create first action", command=self.new_action, width=154, height=40, corner_radius=11, fg_color=PANEL_2, hover_color="#DDE1E8", text_color=TEXT, font=ctk.CTkFont(FONT, 13, "bold")).pack()
        for index, action in enumerate(self.actions):
            selected = index == self.selected_index
            card = ctk.CTkFrame(self.action_list, height=82, corner_radius=14, fg_color="#E8F2FF" if selected else "#F6F7F9", border_width=2 if selected else 0, border_color=BORDER_ACTIVE)
            card.grid(row=index, column=0, sticky="ew", padx=4, pady=4)
            card.grid_propagate(False)
            card.grid_columnconfigure(2, weight=1)
            toggle = ctk.CTkSwitch(card, text="", width=34, onvalue=True, offvalue=False, progress_color=ACCENT, button_color=TEXT, button_hover_color="#FFFFFF", command=lambda i=index: self.toggle_action(i))
            toggle.grid(row=0, column=0, rowspan=2, padx=(12, 7))
            toggle.select() if action.enabled else toggle.deselect()
            badge = ctk.CTkLabel(card, text=f"{index + 1:02}", width=30, height=30, corner_radius=8, fg_color=PANEL_2, font=ctk.CTkFont("Consolas", 10, "bold"), text_color=MUTED)
            badge.grid(row=0, column=1, rowspan=2, padx=(0, 11))
            ctk.CTkLabel(card, text=KIND_NAMES[action.kind], font=ctk.CTkFont(FONT, 13, "bold"), text_color=TEXT if action.enabled else SUBTLE).grid(row=0, column=2, sticky="sw", pady=(8, 0))
            ctk.CTkLabel(card, text=self._target_text(action), font=ctk.CTkFont(FONT, 11), text_color=MUTED if action.enabled else SUBTLE).grid(row=1, column=2, sticky="nw", pady=(0, 7))
            meta = f"×{action.repeats}   ·   wait {action.delay_after:g}s"
            ctk.CTkLabel(card, text=meta, font=ctk.CTkFont(FONT, 11, "bold"), text_color=SUBTLE).grid(row=0, column=3, rowspan=2, padx=10)
            ctk.CTkButton(card, text="Edit", command=lambda i=index: self.select_action(i), width=50, height=28, corner_radius=7, fg_color=PANEL_2, hover_color="#E5E5EA", text_color=MUTED, font=ctk.CTkFont(FONT, 11, "bold")).grid(row=0, column=4, rowspan=2, padx=(0, 10))
        self._update_summary()

    def _update_summary(self) -> None:
        active = [a for a in self.actions if a.enabled]
        operations = sum(a.repeats for a in active)
        try:
            cycles = max(1, int(self.repeat_var.get()))
        except ValueError:
            cycles = 1
        total_operations = operations * cycles
        forever = self.repeat_forever_var.get()
        self.summary_var.set(f"{len(active)} active  /  {len(self.actions)} total   ·   {operations} operations per cycle")
        if hasattr(self, "run_summary_label"):
            self.run_summary_label.configure(text=f"{len(active)} active actions")
            scope = "runs until stopped" if forever else f"{total_operations} total operations"
            self.operation_summary_label.configure(text=f"{operations} per cycle  ·  {scope}")

    def _toggle_repeat_mode(self) -> None:
        self.repeat_entry.configure(state="disabled" if self.repeat_forever_var.get() else "normal")
        self._update_summary()

    def select_action(self, index: int) -> None:
        if not 0 <= index < len(self.actions):
            return
        self.selected_index = index
        self.editing_index = index
        action = self.actions[index]
        self.action_type.set(KIND_NAMES[action.kind])
        self.action_value.set(action.value)
        self.x_var.set("0" if action.x is None else str(action.x))
        self.y_var.set("0" if action.y is None else str(action.y))
        self.x2_var.set("0" if action.x2 is None else str(action.x2))
        self.y2_var.set("0" if action.y2 is None else str(action.y2))
        self.amount_var.set(str(action.amount or -3))
        self.duration_var.set(str(action.duration))
        self.action_repeats_var.set(str(action.repeats))
        self.action_delay.set(str(action.delay_after))
        self.add_button.configure(text="Update selected action")
        self.inspector_tab_var.set("Action")
        self._show_inspector("Action")
        self._update_action_fields()
        self._render_actions()

    def toggle_action(self, index: int) -> None:
        self.actions[index].enabled = not self.actions[index].enabled
        self._render_actions()

    def duplicate_selected(self) -> None:
        if self.selected_index is None:
            return
        clone = copy.deepcopy(self.actions[self.selected_index])
        self.actions.insert(self.selected_index + 1, clone)
        self.selected_index += 1
        self.editing_index = None
        self._render_actions()
        self._set_status("Action duplicated", SUCCESS)

    def delete_selected(self) -> None:
        if self.selected_index is None:
            return
        del self.actions[self.selected_index]
        self.selected_index = min(self.selected_index, len(self.actions) - 1) if self.actions else None
        self.editing_index = None
        self.add_button.configure(text="Add to sequence")
        self._render_actions()

    def move_selected(self, offset: int) -> None:
        if self.selected_index is None:
            return
        target = self.selected_index + offset
        if 0 <= target < len(self.actions):
            self.actions[self.selected_index], self.actions[target] = self.actions[target], self.actions[self.selected_index]
            self.selected_index = target
            self.editing_index = None
            self._render_actions()

    def clear_all(self) -> None:
        if self.actions and not messagebox.askyesno("Start a new sequence?", "This clears all current actions. Save the profile first if you need it.", parent=self):
            return
        self.actions.clear()
        self.selected_index = None
        self.editing_index = None
        self._render_actions()
        self.new_action()
        self._set_status("New sequence", MUTED)

    def record_position_countdown(self, target: str) -> None:
        self.capture_target = target
        self._capture_tick(2)

    def _capture_tick(self, seconds: int) -> None:
        if seconds > 0:
            self._set_status(f"Capturing in {seconds}…", ACCENT)
            self.run_status_label.configure(text="Move the cursor to the target position")
            self.after(1000, lambda: self._capture_tick(seconds - 1))
        else:
            self.capture_cursor(self.capture_target)

    def capture_cursor(self, target: str = "start") -> None:
        x, y = pyautogui.position()
        if target == "dest":
            self.x2_var.set(str(x))
            self.y2_var.set(str(y))
            label = "Destination captured"
        else:
            self.x_var.set(str(x))
            self.y_var.set(str(y))
            if ACTION_NAMES.get(self.action_type.get(), "key") not in MOUSE_KINDS:
                self.action_type.set("Left click")
                self._update_action_fields()
            label = "Position captured"
        self._set_status(label, SUCCESS)
        self.run_status_label.configure(text=f"Recorded X {x}, Y {y}")

    def _settings_from_form(self) -> RunSettings:
        try:
            settings = RunSettings(
                repeat_count=1 if self.repeat_forever_var.get() else int(self.repeat_var.get()),
                start_delay=float(self.start_delay_var.get()),
                cycle_interval=float(self.cycle_interval_var.get()),
                text_key_interval=float(self.text_interval_var.get()),
                delay_jitter=float(self.jitter_var.get()),
                repeat_forever=self.repeat_forever_var.get(),
                start_hotkey=self.start_hotkey_var.get().strip().lower(),
                capture_hotkey=self.capture_hotkey_var.get().strip().lower(),
                stop_hotkey=self.stop_hotkey_var.get().strip().lower(),
            )
        except ValueError as exc:
            raise ValueError("Run settings must contain valid numbers.") from exc
        settings.validate()
        return settings

    def start_run(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        try:
            settings = self._settings_from_form()
            active = [a for a in self.actions if a.enabled]
            if not active:
                raise ValueError("Add or enable at least one action before starting.")
            actions = copy.deepcopy(self.actions)
            for action in active:
                action.validate(self._reserved_key_parts())
        except ValueError as exc:
            messagebox.showerror("Cannot start", str(exc), parent=self)
            return
        self.stop_event.clear()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.progress.stop()
        if settings.repeat_forever:
            self.progress.configure(mode="indeterminate")
            self.progress.start()
        else:
            self.progress.configure(mode="determinate")
            self.progress.set(0)
        self._set_status("Armed", ACCENT)
        self.worker = threading.Thread(target=self._run_worker, args=(actions, settings), daemon=True)
        self.worker.start()

    def _run_worker(self, actions: list[Action], settings: RunSettings) -> None:
        runner = AutomationRunner(pyautogui)
        try:
            completed = runner.run(actions, settings, self.stop_event, self._thread_progress)
            self.after(0, lambda: self._run_finished("Run completed" if completed else "Stopped by user", completed))
        except pyautogui.FailSafeException:
            self.after(0, lambda: self._run_finished("Stopped by corner fail-safe", False))
        except Exception as exc:
            self.after(0, lambda message=str(exc): self._run_failed(message))

    def _thread_progress(self, phase: str, current: int, total: int) -> None:
        if phase == "timer":
            self.after(0, lambda: (self._set_status("Countdown", ACCENT), self.run_status_label.configure(text=f"Starting in {self.start_delay_var.get()} seconds — switch windows now")))
        else:
            progress_value = 0 if total == 0 else current / total
            cycle_text = f"Cycle {current}  ·  looping until stopped" if total == 0 else f"Cycle {current} of {total}"
            stop_key = self.stop_hotkey_var.get().upper()
            self.after(0, lambda: ((self.progress.set(progress_value) if total else None), self._set_status("Running", SUCCESS), self.run_status_label.configure(text=f"{cycle_text}  ·  {stop_key} stops immediately")))

    def _run_finished(self, message: str, completed: bool) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self._set_status("Complete" if completed else "Stopped", SUCCESS if completed else DANGER)
        self.run_status_label.configure(text=message)
        self.progress.set(1 if completed else 0)
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")

    def _run_failed(self, message: str) -> None:
        self._run_finished("Automation error", False)
        messagebox.showerror("Automation error", message, parent=self)

    def stop_run(self) -> None:
        self.stop_event.set()
        if self.worker and self.worker.is_alive():
            self._set_status("Stopping…", DANGER)
            self.run_status_label.configure(text="Finishing the current input safely")

    def _set_status(self, text: str, color: str) -> None:
        self.status_var.set(f"  {text}  ")
        if color != self._status_target:
            self._status_target = color
            self._status_animation_generation += 1
            self._animate_status_color(color, self._status_animation_generation)

    def _toggle_always_on_top(self) -> None:
        self.attributes("-topmost", self.always_on_top_var.get())

    def save_profile_dialog(self) -> None:
        try:
            settings = self._settings_from_form()
            if not self.actions:
                raise ValueError("There are no actions to save.")
            path = filedialog.asksaveasfilename(parent=self, title="Save automation profile", defaultextension=".kca.json", filetypes=[("KeyClick profiles", "*.kca.json"), ("JSON", "*.json")])
            if path:
                save_profile(path, self.actions, settings)
                self._set_status("Profile saved", SUCCESS)
                self.run_status_label.configure(text=Path(path).name)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Could not save", str(exc), parent=self)

    def load_profile_dialog(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Open automation profile", filetypes=[("KeyClick profiles", "*.kca.json"), ("JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            actions, settings = load_profile(path)
            self.actions = actions
            self.repeat_var.set(str(settings.repeat_count))
            self.repeat_forever_var.set(settings.repeat_forever)
            self.start_delay_var.set(str(settings.start_delay))
            self.cycle_interval_var.set(str(settings.cycle_interval))
            self.text_interval_var.set(str(settings.text_key_interval))
            self.jitter_var.set(str(settings.delay_jitter))
            self.start_hotkey_var.set(settings.start_hotkey)
            self.capture_hotkey_var.set(settings.capture_hotkey)
            self.stop_hotkey_var.set(settings.stop_hotkey)
            self._toggle_repeat_mode()
            self._start_global_hotkeys()
            self.start_button.configure(text=f"Start  {settings.start_hotkey.upper()}")
            self.capture_position_button.configure(text=f"Capture cursor position  {settings.capture_hotkey.upper()}")
            self.selected_index = None
            self.editing_index = None
            self._render_actions()
            self._set_status("Profile loaded", SUCCESS)
            self.run_status_label.configure(text=f"{Path(path).name}  ·  {len(actions)} actions")
        except (ValueError, OSError, TypeError) as exc:
            messagebox.showerror("Could not load", str(exc), parent=self)

    def _reserved_key_parts(self) -> set[str]:
        return {
            part.strip().lower()
            for shortcut in (self.start_hotkey_var.get(), self.capture_hotkey_var.get(), self.stop_hotkey_var.get())
            for part in shortcut.split("+")
            if part.strip()
        }

    @staticmethod
    def _pynput_hotkey(value: str) -> str:
        aliases = {"control": "ctrl", "escape": "esc", "return": "enter", "windows": "cmd", "win": "cmd"}
        special = {"ctrl", "alt", "shift", "cmd", "space", "tab", "enter", "esc", "backspace", "delete", "home", "end", "page_up", "page_down", "up", "down", "left", "right"}
        formatted = []
        for raw_part in value.lower().replace(" ", "").split("+"):
            part = aliases.get(raw_part, raw_part)
            if not part:
                raise ValueError("A shortcut contains an empty key.")
            if part in special or (part.startswith("f") and part[1:].isdigit()):
                formatted.append(f"<{part}>")
            elif len(part) == 1:
                formatted.append(part)
            else:
                raise ValueError(f"Unsupported shortcut key: {raw_part}")
        shortcut = "+".join(formatted)
        keyboard.HotKey.parse(shortcut)
        return shortcut

    def _apply_hotkeys(self) -> None:
        try:
            values = [self.start_hotkey_var.get().strip().lower(), self.capture_hotkey_var.get().strip().lower(), self.stop_hotkey_var.get().strip().lower()]
            if len(set(values)) != 3 or any(not value for value in values):
                raise ValueError("Start, capture, and stop shortcuts must be present and different.")
            for value in values:
                self._pynput_hotkey(value)
            for action in self.actions:
                action.validate(self._reserved_key_parts())
            self._start_global_hotkeys()
            self.start_button.configure(text=f"Start  {values[0].upper()}")
            self.capture_position_button.configure(text=f"Capture cursor position  {values[1].upper()}")
            self._set_status("Shortcuts applied", SUCCESS)
            self.run_status_label.configure(text=f"{values[0].upper()} starts · {values[2].upper()} stops")
        except ValueError as exc:
            messagebox.showerror("Check shortcuts", str(exc), parent=self)

    def _toggle_run(self) -> None:
        if self.worker and self.worker.is_alive():
            self.stop_run()
        else:
            self.start_run()

    def _start_global_hotkeys(self) -> None:
        try:
            mappings = {
                self._pynput_hotkey(self.start_hotkey_var.get()): lambda: self.after(0, self._toggle_run),
                self._pynput_hotkey(self.capture_hotkey_var.get()): lambda: self.after(0, lambda: self.capture_cursor("start")),
                self._pynput_hotkey(self.stop_hotkey_var.get()): lambda: self.after(0, self.stop_run),
            }
            if self.hotkey_listener:
                self.hotkey_listener.stop()
            self.hotkey_listener = keyboard.GlobalHotKeys(mappings)
            self.hotkey_listener.daemon = True
            self.hotkey_listener.start()
        except (ValueError, TypeError):
            self._set_status("GUI controls only", DANGER)

    def _on_close(self) -> None:
        self.stop_event.set()
        if self.key_capture_listener:
            self.key_capture_listener.stop()
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        self.destroy()


def main() -> int:
    app = AutomatorApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
