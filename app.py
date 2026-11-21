from __future__ import annotations

import importlib
import json
import math
import queue
import statistics
import sys
import threading
import tkinter as tk
import time
from pathlib import Path
from tkinter import ttk
from typing import Any


VENDOR_ID = 0x17B5
PRODUCT_ID = 0x0010
REPORT_ID = 0
REPORT_LENGTH = 64
POSES = ("neutral", "left", "right", "forward", "back")
POSE_LABELS = {
    "neutral": "Mitte",
    "left": "Links",
    "right": "Rechts",
    "forward": "Vor",
    "back": "Zurück",
}
DEFAULT_CALIBRATION = {
    "neutral": {"x": 336, "y": 397},
    "left": {"x": 488, "y": 368},
    "right": {"x": 189, "y": 366},
    "forward": {"x": 348, "y": 554},
    "back": {"x": 328, "y": 242},
}
DEFAULT_KEYS = {"forward": "W", "back": "S", "left": "A", "right": "D"}
KEY_NAMES = {
    "SPACE": 0x20,
    "ENTER": 0x0D,
    "TAB": 0x09,
    "ESC": 0x1B,
    "BACKSPACE": 0x08,
    "DELETE": 0x2E,
    "UP": 0x26,
    "DOWN": 0x28,
    "LEFT": 0x25,
    "RIGHT": 0x27,
    "SHIFT": 0x10,
    "CTRL": 0x11,
    "ALT": 0x12,
    "CAPSLOCK": 0x14,
    "HOME": 0x24,
    "END": 0x23,
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
    "INSERT": 0x2D,
}
AXIS_SETTINGS = (
    ("forward", "Vor", "y", -1),
    ("back", "Zurück", "y", 1),
    ("left", "Links", "x", -1),
    ("right", "Rechts", "x", 1),
)
SETTINGS_PATH = Path(__file__).with_name("settings.json")


def parse_report(report: bytes | bytearray | list[int]) -> tuple[int, int] | None:
    """Decode the MFT's signed big-endian X/Y values."""
    data = bytes(report)
    if len(data) == REPORT_LENGTH + 1:
        if data[0] != REPORT_ID:
            return None
        data = data[1:]
    elif len(data) < 4:
        return None

    return int.from_bytes(data[2:4], "big", signed=True), int.from_bytes(
        data[0:2], "big", signed=True
    )


def normalize_axis(value: float, center: float, negative: float, positive: float) -> float:
    delta = value - center
    negative_delta = negative - center
    positive_delta = positive - center
    if delta * negative_delta > 0:
        return -min(1.0, abs(delta / negative_delta))
    if delta * positive_delta > 0:
        return min(1.0, abs(delta / positive_delta))
    return 0.0


def calibration_is_valid(calibration: dict[str, dict[str, float]]) -> bool:
    try:
        values = [calibration[pose][axis] for pose in POSES for axis in ("x", "y")]
    except (KeyError, TypeError):
        return False
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values):
        return False
    neutral = calibration["neutral"]
    return (
        (calibration["left"]["x"] - neutral["x"])
        * (calibration["right"]["x"] - neutral["x"])
        < 0
        and (calibration["forward"]["y"] - neutral["y"])
        * (calibration["back"]["y"] - neutral["y"])
        < 0
    )


def key_code(name: str) -> int:
    normalized = name.strip().upper()
    if len(normalized) == 1 and normalized.isascii() and normalized.isalnum():
        return ord(normalized)
    if normalized.startswith("F") and normalized[1:].isdigit():
        function_key = int(normalized[1:])
        if 1 <= function_key <= 24:
            return 0x70 + function_key - 1
    if normalized in KEY_NAMES:
        return KEY_NAMES[normalized]
    raise ValueError(f"Nicht unterstützte Taste: {name}")


def normalize_key_name(name: str) -> str:
    normalized = name.strip().upper()
    key_code(normalized)
    return normalized


def calibrated_direction_vector(
    calibration: dict[str, dict[str, float]], raw_x: float, raw_y: float
) -> tuple[float, float]:
    center = calibration["neutral"]
    x = normalize_axis(
        raw_x, center["x"], calibration["left"]["x"], calibration["right"]["x"]
    )
    y = normalize_axis(
        raw_y, center["y"], calibration["forward"]["y"], calibration["back"]["y"]
    )
    forward_x = normalize_axis(
        calibration["forward"]["x"],
        center["x"],
        calibration["left"]["x"],
        calibration["right"]["x"],
    )
    back_x = normalize_axis(
        calibration["back"]["x"],
        center["x"],
        calibration["left"]["x"],
        calibration["right"]["x"],
    )
    left_y = normalize_axis(
        calibration["left"]["y"],
        center["y"],
        calibration["forward"]["y"],
        calibration["back"]["y"],
    )
    right_y = normalize_axis(
        calibration["right"]["y"],
        center["y"],
        calibration["forward"]["y"],
        calibration["back"]["y"],
    )
    x_cross = -y * forward_x if y < 0 else y * back_x
    y_cross = -x * left_y if x < 0 else x * right_y
    return max(-1.0, min(1.0, x - x_cross)), max(-1.0, min(1.0, y - y_cross))


def neutral_sensor_offset(
    raw_position: tuple[float, float], calibrated_neutral: dict[str, float]
) -> tuple[float, float]:
    return (
        raw_position[0] - calibrated_neutral["x"],
        raw_position[1] - calibrated_neutral["y"],
    )


def resolve_mapped_keys(
    vector: tuple[float, float],
    key_map: dict[str, str],
    deadzone: float,
    pressed_axes: dict[str, int],
) -> tuple[set[str], dict[str, int]]:
    active_axes = dict(pressed_axes)
    desired: set[str] = set()
    for direction, _, axis, sign in AXIS_SETTINGS:
        component = vector[0] if axis == "x" else vector[1]
        current_sign = active_axes.get(axis, 0)
        if current_sign == sign:
            active = component * sign > deadzone * 0.55
        else:
            active = component * sign >= deadzone
        if active:
            active_axes[axis] = sign
            desired.add(key_map[direction])
        elif current_sign == sign:
            active_axes.pop(axis, None)
    return desired, active_axes


def _read_settings() -> tuple[dict[str, Any], str | None]:
    defaults = {
        "calibration": DEFAULT_CALIBRATION,
        "keys": DEFAULT_KEYS,
        "deadzone": 0.22,
    }
    if not SETTINGS_PATH.exists():
        return defaults, None

    try:
        loaded = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("Die Einstellungsdatei muss ein JSON-Objekt enthalten.")
        calibration = loaded.get("calibration", {})
        keys = loaded.get("keys", {})
        deadzone = float(loaded.get("deadzone", defaults["deadzone"]))
        if calibration_is_valid(calibration):
            defaults["calibration"] = calibration
        for direction in DEFAULT_KEYS:
            if direction in keys:
                defaults["keys"][direction] = normalize_key_name(keys[direction])
        if math.isfinite(deadzone) and 0.05 <= deadzone <= 0.8:
            defaults["deadzone"] = deadzone
        return defaults, None
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        return defaults, f"Einstellungen konnten nicht geladen werden: {error}"


class KeyboardOutput:
    def __init__(self) -> None:
        self.pressed: set[str] = set()
        try:
            keyboard = importlib.import_module("pynput.keyboard")
        except (ImportError, OSError) as error:
            raise RuntimeError(
                "Tastatursteuerung konnte nicht initialisiert werden. "
                "Unter macOS wird Bedienungshilfen-Zugriff benötigt; "
                "unter Linux eine X11-Sitzung."
            ) from error
        self.controller = keyboard.Controller()
        self.key_type = keyboard.Key

    def _key(self, name: str) -> Any:
        normalized = normalize_key_name(name)
        if len(normalized) == 1 and normalized.isalnum():
            return normalized.lower()
        if normalized.startswith("F") and normalized[1:].isdigit():
            return getattr(self.key_type, normalized.lower())
        aliases = {
            "SPACE": "space",
            "ENTER": "enter",
            "ESC": "esc",
            "CTRL": "ctrl",
            "CAPSLOCK": "caps_lock",
            "PAGEUP": "page_up",
            "PAGEDOWN": "page_down",
        }
        return getattr(self.key_type, aliases.get(normalized, normalized.lower()))

    def set_pressed(self, desired: set[str]) -> None:
        for name in sorted(self.pressed - desired):
            self.controller.release(self._key(name))
            self.pressed.remove(name)
        for name in sorted(desired - self.pressed):
            self.controller.press(self._key(name))
            self.pressed.add(name)

    def release_all(self) -> None:
        self.set_pressed(set())


class SensorReader:
    def __init__(self) -> None:
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _read(self) -> None:
        device = None
        try:
            if sys.platform == "win32":
                self._read_windows()
            elif sys.platform in ("darwin", "linux"):
                self._read_hidapi()
            else:
                raise OSError(f"Dieses Betriebssystem wird nicht unterstützt: {sys.platform}")
        except Exception as error:
            if not self._stop.is_set():
                self.events.put(("error", str(error)))
        finally:
            self.events.put(("disconnected", None))

    def _read_windows(self) -> None:
        hid = importlib.import_module("pywinusb.hid")
        devices = hid.HidDeviceFilter(
            vendor_id=VENDOR_ID, product_id=PRODUCT_ID
        ).get_devices()
        if not devices:
            raise OSError("MFT Sensor (VID 17B5 / PID 0010) wurde nicht gefunden.")
        device = devices[0]
        device.open()
        try:
            def handle_report(report: list[int]) -> None:
                coordinates = parse_report(report)
                if coordinates is not None and not self._stop.is_set():
                    self.events.put(("sample", coordinates))

            device.set_raw_data_handler(handle_report)
            self.events.put(("connected", device.product_name or "MFT Sensor"))
            while not self._stop.wait(0.1):
                pass
        finally:
            device.close()

    def _read_hidapi(self) -> None:
        hid = importlib.import_module("hid")
        devices = hid.enumerate(VENDOR_ID, PRODUCT_ID)
        if not devices:
            raise OSError("MFT Sensor (VID 17B5 / PID 0010) wurde nicht gefunden.")
        device = hid.device()
        device.open_path(devices[0]["path"])
        try:
            product_name = devices[0].get("product_string") or "MFT Sensor"
            self.events.put(("connected", product_name))
            while not self._stop.is_set():
                report = device.read(REPORT_LENGTH + 1, timeout_ms=100)
                coordinates = parse_report(report) if report else None
                if coordinates is not None:
                    self.events.put(("sample", coordinates))
        finally:
            device.close()


class MFTDriverApp:
    BG = "#151a17"
    PANEL = "#202722"
    RAISED = "#29332c"
    LINE = "#3a453d"
    TEXT = "#f1f3eb"
    MUTED = "#a2ada3"
    LIME = "#c3f36b"
    CORAL = "#ff8068"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("MFT Motion Keys")
        self.root.geometry("960x760")
        self.root.minsize(760, 560)
        self.root.configure(bg=self.BG)
        self.settings, warning = _read_settings()
        self.calibration = self.settings["calibration"]
        self.key_map = dict(self.settings["keys"])
        self.deadzone = self.settings["deadzone"]
        self.keyboard: KeyboardOutput | None = None
        self.keyboard_error: str | None = None
        try:
            self.keyboard = KeyboardOutput()
        except (ImportError, OSError, RuntimeError) as error:
            self.keyboard_error = str(error)
        self.reader = SensorReader()
        self.sensor_connected = False
        self.sensor_ready = False
        self.reader_failed = False
        self.last_report_at = 0.0
        self.report_timeout_notified = False
        self.keyboard_enabled = False
        self.calibration_samples: list[tuple[int, int]] = []
        self.samples: list[tuple[int, int]] = []
        self.zero_offset = (0, 0)
        self.smoothed: tuple[float, float] | None = None
        self.capture_pose: str | None = None
        self.pressed_axes: dict[str, int] = {}
        self.key_vars = {direction: tk.StringVar(value=self.key_map[direction]) for direction in DEFAULT_KEYS}
        self.status_var = tk.StringVar(value=warning or "Board verbinden, um loszulegen.")
        self.value_var = tk.StringVar(value="X 0.00     Y 0.00")
        self.output_var = tk.StringVar(value="Tastaturausgabe pausiert")
        self.deadzone_var = tk.DoubleVar(value=self.deadzone)
        self._build_ui()
        self.root.bind("<KeyPress>", self._capture_key)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(25, self._process_events)
        if warning:
            self._set_status(warning, error=True)

    def _build_ui(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "MFT.Horizontal.TProgressbar",
            background=self.LIME,
            troughcolor=self.RAISED,
            bordercolor=self.RAISED,
            lightcolor=self.LIME,
            darkcolor=self.LIME,
        )
        style.configure(
            "MFT.TButton",
            background=self.RAISED,
            foreground=self.TEXT,
            bordercolor=self.LINE,
            padding=(12, 9),
            font=("Segoe UI", 10, "bold"),
        )
        style.map("MFT.TButton", background=[("active", "#39463b")])
        style.configure(
            "MFT.Primary.TButton",
            background=self.LIME,
            foreground="#172014",
            bordercolor=self.LIME,
            padding=(12, 10),
            font=("Segoe UI", 10, "bold"),
        )
        style.map("MFT.Primary.TButton", background=[("active", "#d2ff85")])
        style.configure(
            "Horizontal.TScale",
            background=self.PANEL,
            troughcolor=self.RAISED,
        )

        viewport = tk.Frame(self.root, bg=self.BG)
        viewport.pack(fill="both", expand=True)
        self.scroll_canvas = tk.Canvas(
            viewport, bg=self.BG, highlightthickness=0, borderwidth=0
        )
        scrollbar = ttk.Scrollbar(
            viewport, orient="vertical", command=self.scroll_canvas.yview
        )
        self.scroll_canvas.configure(yscrollcommand=scrollbar.set)
        self.scroll_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        shell = tk.Frame(self.scroll_canvas, bg=self.BG, padx=28, pady=20)
        self.scroll_window = self.scroll_canvas.create_window(
            (0, 0), window=shell, anchor="nw"
        )
        shell.bind(
            "<Configure>",
            lambda _event: self.scroll_canvas.configure(
                scrollregion=self.scroll_canvas.bbox("all")
            ),
        )
        self.scroll_canvas.bind(
            "<Configure>",
            lambda event: self.scroll_canvas.itemconfigure(
                self.scroll_window, width=event.width
            ),
        )
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)
        self.root.bind_all("<Button-4>", self._on_linux_scroll)
        self.root.bind_all("<Button-5>", self._on_linux_scroll)

        header = tk.Frame(shell, bg=self.BG)
        header.pack(fill="x", pady=(0, 17))
        logo = tk.Label(
            header,
            text="M",
            bg=self.LIME,
            fg="#172014",
            font=("Segoe UI Black", 18, "bold"),
            width=3,
            height=1,
        )
        logo.pack(side="left", padx=(0, 12))
        title = tk.Frame(header, bg=self.BG)
        title.pack(side="left")
        tk.Label(
            title, text="MFT MOTION KEYS", bg=self.BG, fg=self.TEXT, font=("Segoe UI", 20, "bold")
        ).pack(anchor="w")
        tk.Label(
            title,
            text="USB-Board als Tastatursteuerung",
            bg=self.BG,
            fg=self.MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w")
        self.connection_badge = tk.Label(
            header,
            text="●  NICHT VERBUNDEN",
            bg=self.BG,
            fg=self.MUTED,
            font=("Segoe UI", 9, "bold"),
        )
        self.connection_badge.pack(side="right", anchor="n", pady=10)

        content = tk.Frame(shell, bg=self.BG)
        content.pack(fill="both", expand=True)
        left = tk.Frame(content, bg=self.BG, width=408)
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))
        right = tk.Frame(content, bg=self.BG, width=400)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))

        self._card_heading(left, "Verbindung", "USB-Sensor")
        self._connection_card(left)
        self._card_heading(left, "Tastenzuweisung", "Taste drücken zum Ändern")
        self._mapping_card(left)
        self._card_heading(right, "Bewegung", "Live-Sensorwerte")
        self._motion_card(right)
        self._card_heading(right, "Kalibrierung", "Haltung aufnehmen")
        self._calibration_card(right)

        footer = tk.Frame(shell, bg=self.PANEL, padx=14, pady=11)
        footer.pack(fill="x", pady=(15, 0))
        tk.Label(
            footer,
            textvariable=self.status_var,
            bg=self.PANEL,
            fg=self.TEXT,
            font=("Segoe UI", 9),
            anchor="w",
            wraplength=790,
        ).pack(fill="x")

    def _card_heading(self, parent: tk.Widget, title: str, subtitle: str) -> None:
        row = tk.Frame(parent, bg=self.BG)
        row.pack(fill="x", pady=(8, 7))
        tk.Label(row, text=title, bg=self.BG, fg=self.TEXT, font=("Segoe UI", 12, "bold")).pack(
            side="left"
        )
        tk.Label(row, text=subtitle, bg=self.BG, fg=self.MUTED, font=("Segoe UI", 8)).pack(
            side="right", anchor="s"
        )

    def _card(self, parent: tk.Widget) -> tk.Frame:
        frame = tk.Frame(parent, bg=self.PANEL, highlightthickness=1, highlightbackground=self.LINE)
        frame.pack(fill="x", pady=(0, 5))
        return frame

    def _connection_card(self, parent: tk.Widget) -> None:
        card = self._card(parent)
        inner = tk.Frame(card, bg=self.PANEL, padx=15, pady=13)
        inner.pack(fill="x")
        tk.Label(
            inner,
            text="MFT Sensor  ·  USB HID  ·  VID 17B5 / PID 0010",
            bg=self.PANEL,
            fg=self.TEXT,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        buttons = tk.Frame(inner, bg=self.PANEL)
        buttons.pack(fill="x", pady=(12, 0))
        self.connect_button = ttk.Button(
            buttons,
            text="Board verbinden",
            command=self._toggle_connection,
            style="MFT.Primary.TButton",
        )
        self.connect_button.pack(side="left")
        self.output_button = ttk.Button(
            buttons,
            text="Tastenausgabe starten",
            command=self._toggle_output,
            style="MFT.TButton",
        )
        self.output_button.pack(side="left", padx=(8, 0))
        tk.Label(
            inner,
            text="Tasten werden im aktiven Vordergrundfenster gedrückt gehalten.",
            bg=self.PANEL,
            fg=self.MUTED,
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(9, 0))

    def _mapping_card(self, parent: tk.Widget) -> None:
        card = self._card(parent)
        inner = tk.Frame(card, bg=self.PANEL, padx=15, pady=8)
        inner.pack(fill="x")
        for direction, label, _, _ in AXIS_SETTINGS:
            row = tk.Frame(inner, bg=self.PANEL)
            row.pack(fill="x", pady=4)
            tk.Label(
                row, text=label, width=12, anchor="w", bg=self.PANEL, fg=self.TEXT, font=("Segoe UI", 9)
            ).pack(side="left")
            entry = tk.Entry(
                row,
                textvariable=self.key_vars[direction],
                width=10,
                justify="center",
                state="readonly",
                readonlybackground=self.RAISED,
                fg=self.LIME,
                relief="flat",
                font=("Segoe UI", 10, "bold"),
            )
            entry.pack(side="left", padx=(0, 9), ipady=5)
            button = ttk.Button(
                row,
                text="Taste ändern",
                style="MFT.TButton",
                command=lambda value=direction: self._begin_key_capture(value),
            )
            button.pack(side="left")

        scale_row = tk.Frame(inner, bg=self.PANEL)
        scale_row.pack(fill="x", pady=(9, 1))
        tk.Label(
            scale_row, text="Empfindlichkeit", width=12, anchor="w", bg=self.PANEL, fg=self.TEXT, font=("Segoe UI", 9)
        ).pack(side="left")
        ttk.Scale(
            scale_row,
            from_=0.08,
            to=0.55,
            variable=self.deadzone_var,
            command=self._change_deadzone,
            style="Horizontal.TScale",
        ).pack(side="left", fill="x", expand=True, padx=(0, 9))
        self.deadzone_label = tk.Label(
            scale_row,
            text=f"{self.deadzone:.2f}",
            bg=self.PANEL,
            fg=self.MUTED,
            font=("Segoe UI", 9, "bold"),
            width=4,
        )
        self.deadzone_label.pack(side="left")
        tk.Label(
            inner,
            text="Beim Kippen werden Vor/Zurück sowie Links/Rechts unabhängig kombiniert.",
            bg=self.PANEL,
            fg=self.MUTED,
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(9, 1))

    def _motion_card(self, parent: tk.Widget) -> None:
        card = self._card(parent)
        inner = tk.Frame(card, bg=self.PANEL, padx=15, pady=13)
        inner.pack(fill="x")
        self.motion_canvas = tk.Canvas(
            inner, width=340, height=202, bg=self.PANEL, highlightthickness=0
        )
        self.motion_canvas.pack(fill="x")
        self._draw_motion(0.0, 0.0)
        row = tk.Frame(inner, bg=self.PANEL)
        row.pack(fill="x", pady=(8, 0))
        tk.Label(
            row, textvariable=self.value_var, bg=self.PANEL, fg=self.LIME, font=("Consolas", 11, "bold")
        ).pack(side="left")
        tk.Label(
            row, textvariable=self.output_var, bg=self.PANEL, fg=self.MUTED, font=("Segoe UI", 8)
        ).pack(side="right")
        self.axis_bars: dict[str, ttk.Progressbar] = {}
        for label, axis in (("Links ↔ Rechts", "x"), ("Vor ↔ Zurück", "y")):
            bar_row = tk.Frame(inner, bg=self.PANEL)
            bar_row.pack(fill="x", pady=(8, 0))
            tk.Label(
                bar_row, text=label, bg=self.PANEL, fg=self.MUTED, font=("Segoe UI", 8), width=18, anchor="w"
            ).pack(side="left")
            progress = ttk.Progressbar(
                bar_row, style="MFT.Horizontal.TProgressbar", maximum=100, mode="determinate"
            )
            progress.pack(side="left", fill="x", expand=True)
            self.axis_bars[axis] = progress

    def _calibration_card(self, parent: tk.Widget) -> None:
        card = self._card(parent)
        inner = tk.Frame(card, bg=self.PANEL, padx=15, pady=9)
        inner.pack(fill="x")
        tk.Label(
            inner,
            text="Board verbinden, Haltung einnehmen und 60 Werte aufnehmen.",
            bg=self.PANEL,
            fg=self.MUTED,
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(0, 7))
        grid = tk.Frame(inner, bg=self.PANEL)
        grid.pack(fill="x")
        for index, pose in enumerate(POSES):
            row, column = divmod(index, 3)
            button = ttk.Button(
                grid,
                text=POSE_LABELS[pose],
                style="MFT.TButton",
                command=lambda value=pose: self._capture_pose(value),
            )
            button.grid(row=row, column=column, padx=(0, 6), pady=4, sticky="ew")
        for column in range(3):
            grid.columnconfigure(column, weight=1)
        self.calibration_label = tk.Label(
            inner,
            text=self._calibration_summary(),
            bg=self.PANEL,
            fg=self.MUTED,
            font=("Consolas", 8),
            justify="left",
            anchor="w",
        )
        self.calibration_label.pack(fill="x", pady=(6, 0))

    def _calibration_summary(self) -> str:
        return "  ·  ".join(
            f"{POSE_LABELS[pose]} {self.calibration[pose]['x']},{self.calibration[pose]['y']}"
            for pose in POSES
        )

    def _draw_motion(self, x: float, y: float) -> None:
        canvas = self.motion_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 340)
        height = max(canvas.winfo_height(), 202)
        center_x, center_y = width / 2, height / 2
        radius = min(width, height) * 0.34
        canvas.create_oval(
            center_x - radius,
            center_y - radius,
            center_x + radius,
            center_y + radius,
            outline=self.LINE,
            width=2,
        )
        canvas.create_line(center_x - radius, center_y, center_x + radius, center_y, fill=self.LINE)
        canvas.create_line(center_x, center_y - radius, center_x, center_y + radius, fill=self.LINE)
        canvas.create_text(center_x, center_y - radius - 12, text="VOR", fill=self.MUTED, font=("Segoe UI", 8))
        canvas.create_text(center_x, center_y + radius + 12, text="ZURÜCK", fill=self.MUTED, font=("Segoe UI", 8))
        canvas.create_text(center_x - radius - 21, center_y, text="LINKS", fill=self.MUTED, font=("Segoe UI", 8))
        canvas.create_text(center_x + radius + 22, center_y, text="RECHTS", fill=self.MUTED, font=("Segoe UI", 8))
        dot_x = center_x + x * radius
        dot_y = center_y + y * radius
        canvas.create_oval(dot_x - 8, dot_y - 8, dot_x + 8, dot_y + 8, fill=self.LIME, outline="")

    def _set_status(self, message: str, error: bool = False) -> None:
        self.status_var.set(message)
        self.root.update_idletasks()
        if error:
            self.connection_badge.configure(fg=self.CORAL, text="●  FEHLER")

    def _on_mousewheel(self, event: tk.Event) -> str:
        self.scroll_canvas.yview_scroll(-int(event.delta / 120), "units")
        return "break"

    def _on_linux_scroll(self, event: tk.Event) -> str:
        self.scroll_canvas.yview_scroll(-1 if event.num == 4 else 1, "units")
        return "break"

    def _toggle_connection(self) -> None:
        if self.reader.running:
            self.reader.stop()
            self._release_keys()
            self._set_status("Trenne USB-Verbindung …")
            return
        self.sensor_ready = False
        self.reader_failed = False
        self.samples.clear()
        self.smoothed = None
        self.zero_offset = (0, 0)
        self.reader.start()
        self.connect_button.configure(text="Verbindung trennen")
        self._set_status("Suche MFT Sensor …")

    def _toggle_output(self) -> None:
        if not self.sensor_connected or not self.sensor_ready:
            self._set_status("Zuerst das Board verbinden und die Ruhelage einmessen.")
            return
        if self.keyboard is None:
            try:
                self.keyboard = KeyboardOutput()
                self.keyboard_error = None
            except (ImportError, OSError, RuntimeError) as error:
                self.keyboard_error = str(error)
                self._set_status(f"Tastatursteuerung nicht verfügbar: {error}", error=True)
                return
        self.keyboard_enabled = not self.keyboard_enabled
        if not self.keyboard_enabled:
            self._release_keys()
        self.output_button.configure(
            text="Tastenausgabe pausieren" if self.keyboard_enabled else "Tastenausgabe starten"
        )
        self.output_var.set("Tastaturausgabe aktiv" if self.keyboard_enabled else "Tastaturausgabe pausiert")
        self._set_status(
            "Tastatursteuerung aktiv. Wechsle ins gewünschte Spiel oder Programm."
            if self.keyboard_enabled
            else "Tastatursteuerung pausiert."
        )

    def _begin_key_capture(self, direction: str) -> None:
        self.capture_pose = None
        self._capture_key_direction = direction
        self._set_status(f"Neue Taste für {POSE_LABELS[direction].lower()} drücken – Esc bricht ab.")
        self.root.focus_force()

    def _capture_key(self, event: tk.Event) -> str | None:
        direction = getattr(self, "_capture_key_direction", None)
        if not direction:
            return None
        del self._capture_key_direction
        if event.keysym == "Escape":
            self._set_status("Tastenzuweisung abgebrochen.")
            return "break"
        aliases = {"space": "SPACE", "Return": "ENTER", "BackSpace": "BACKSPACE"}
        name = aliases.get(event.keysym, event.keysym.upper())
        try:
            normalized = normalize_key_name(name)
            self.key_map[direction] = normalized
            self.key_vars[direction].set(normalized)
            self._save_settings()
            self._set_status(f"{POSE_LABELS[direction]} steuert jetzt die Taste {normalized}.")
        except ValueError as error:
            self._set_status(str(error), error=True)
        return "break"

    def _change_deadzone(self, value: str) -> None:
        self.deadzone = float(value)
        self.deadzone_label.configure(text=f"{self.deadzone:.2f}")
        self._save_settings()

    def _capture_pose(self, pose: str) -> None:
        if not self.sensor_connected or not self.sensor_ready:
            self._set_status("Verbinde zuerst das Board und warte auf die Ruhelage.")
            return
        if pose == "neutral":
            self._release_keys()
        self.capture_pose = pose
        self.calibration_samples.clear()
        self._set_status(f"{POSE_LABELS[pose]} wird aufgenommen … Board ruhig in dieser Haltung halten.")

    def _save_settings(self) -> None:
        self.settings = {
            "calibration": self.calibration,
            "keys": self.key_map,
            "deadzone": self.deadzone,
        }
        try:
            SETTINGS_PATH.write_text(
                json.dumps(self.settings, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as error:
            self._set_status(f"Einstellungen konnten nicht gespeichert werden: {error}", error=True)

    def _process_events(self) -> None:
        while True:
            try:
                kind, value = self.reader.events.get_nowait()
            except queue.Empty:
                break
            if kind == "connected":
                self.sensor_connected = True
                self.last_report_at = time.monotonic()
                self.report_timeout_notified = False
                self.connection_badge.configure(fg=self.LIME, text="●  VERBUNDEN")
                self.connect_button.configure(text="Verbindung trennen")
                self._set_status(f"Verbunden mit {value}. Ruhelage wird eingemessen …")
            elif kind == "sample":
                self._handle_sample(value)
            elif kind == "error":
                self.reader_failed = True
                self._set_status(f"USB-Fehler: {value}", error=True)
            elif kind == "disconnected":
                was_connected = self.sensor_connected
                self.sensor_connected = False
                self.sensor_ready = False
                self.last_report_at = 0.0
                self.report_timeout_notified = False
                self.keyboard_enabled = False
                self.connect_button.configure(text="Board verbinden")
                self.output_button.configure(text="Tastenausgabe starten")
                self.output_var.set("Tastaturausgabe pausiert")
                if not self.reader_failed:
                    self.connection_badge.configure(fg=self.MUTED, text="●  NICHT VERBUNDEN")
                self._release_keys()
                if was_connected and not self.reader_failed:
                    self._set_status("USB-Verbindung getrennt.")
        if (
            self.sensor_connected
            and self.sensor_ready
            and not self.report_timeout_notified
            and time.monotonic() - self.last_report_at > 1.0
        ):
            self.report_timeout_notified = True
            self.reader.stop()
            self.keyboard_enabled = False
            self.output_button.configure(text="Tastenausgabe starten")
            self.output_var.set("Tastaturausgabe pausiert")
            self._release_keys()
            self._set_status("Keine Sensordaten mehr empfangen; Tasten freigegeben.", error=True)
        self.root.after(25, self._process_events)

    def _handle_sample(self, raw: tuple[int, int]) -> None:
        self.last_report_at = time.monotonic()
        if not self.sensor_ready:
            self.samples.append(raw)
            if len(self.samples) < 48:
                self._set_status(f"Ruhelage einmessen … {len(self.samples)}/48")
                return
            stable = self.samples[-32:]
            center_x = statistics.median(point[0] for point in stable)
            center_y = statistics.median(point[1] for point in stable)
            self.zero_offset = (
                center_x - self.calibration["neutral"]["x"],
                center_y - self.calibration["neutral"]["y"],
            )
            self.smoothed = (center_x, center_y)
            self.sensor_ready = True
            self._set_status("Board bereit. Tastensteuerung bei Bedarf aktivieren.")
            return

        self.samples.append(raw)
        if len(self.samples) > 5:
            self.samples.pop(0)
        filtered = (
            statistics.median(point[0] for point in self.samples),
            statistics.median(point[1] for point in self.samples),
        )
        if self.smoothed is None:
            self.smoothed = filtered
        else:
            self.smoothed = (
                self.smoothed[0] + (filtered[0] - self.smoothed[0]) * 0.55,
                self.smoothed[1] + (filtered[1] - self.smoothed[1]) * 0.55,
            )

        adjusted_x = self.smoothed[0] - self.zero_offset[0]
        adjusted_y = self.smoothed[1] - self.zero_offset[1]
        vector = self._direction_vector(adjusted_x, adjusted_y)
        self._show_motion(vector)

        if self.capture_pose is not None:
            self.calibration_samples.append(
                (int(round(adjusted_x)), int(round(adjusted_y)))
            )
            if len(self.calibration_samples) >= 60:
                self._finish_calibration()
            return
        self._update_keyboard(vector)

    def _direction_vector(self, raw_x: float, raw_y: float) -> tuple[float, float]:
        return calibrated_direction_vector(self.calibration, raw_x, raw_y)

    def _show_motion(self, vector: tuple[float, float]) -> None:
        self.value_var.set(f"X {vector[0]:+.2f}     Y {vector[1]:+.2f}")
        self.axis_bars["x"]["value"] = (vector[0] + 1) * 50
        self.axis_bars["y"]["value"] = (vector[1] + 1) * 50
        self._draw_motion(vector[0], vector[1])

    def _update_keyboard(self, vector: tuple[float, float]) -> None:
        if not self.keyboard_enabled or self.keyboard is None:
            return
        desired, self.pressed_axes = resolve_mapped_keys(
            vector, self.key_map, self.deadzone, self.pressed_axes
        )
        try:
            self.keyboard.set_pressed(desired)
        except (OSError, ValueError) as error:
            self.keyboard_enabled = False
            self.output_button.configure(text="Tastenausgabe starten")
            self.output_var.set("Tastaturausgabe pausiert")
            self._release_keys()
            self._set_status(f"Tastaturausgabe fehlgeschlagen: {error}", error=True)

    def _finish_calibration(self) -> None:
        pose = self.capture_pose
        if pose is None:
            return
        candidate = {name: dict(values) for name, values in self.calibration.items()}
        candidate[pose] = {
            "x": statistics.median(sample[0] for sample in self.calibration_samples),
            "y": statistics.median(sample[1] for sample in self.calibration_samples),
        }
        self.capture_pose = None
        self.calibration_samples.clear()
        if not calibration_is_valid(candidate):
            self._set_status(
                "Kalibrierung verworfen: Mitte muss zwischen den Endpunkten jeder Achse liegen.",
                error=True,
            )
            return
        if pose == "neutral" and self.smoothed is not None:
            self.zero_offset = neutral_sensor_offset(
                self.smoothed, candidate["neutral"]
            )
        self.calibration = candidate
        self.calibration_label.configure(text=self._calibration_summary())
        self._save_settings()
        if pose == "neutral" and self.smoothed is not None:
            centered = self._direction_vector(
                self.smoothed[0] - self.zero_offset[0],
                self.smoothed[1] - self.zero_offset[1],
            )
            self._show_motion(centered)
            self._update_keyboard(centered)
        self._set_status(f"{POSE_LABELS[pose]} gespeichert.")

    def _release_keys(self) -> None:
        self.pressed_axes.clear()
        if self.keyboard is None:
            return
        try:
            self.keyboard.release_all()
        except (OSError, ValueError) as error:
            self._set_status(f"Tasten konnten nicht freigegeben werden: {error}", error=True)

    def _close(self) -> None:
        self.keyboard_enabled = False
        self._release_keys()
        self.reader.stop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    MFTDriverApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
