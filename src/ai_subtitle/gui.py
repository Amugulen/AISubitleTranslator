from __future__ import annotations

import os
import random
import traceback
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Callable, Dict, Optional, Tuple

from ai_subtitle.config import (
    build_config,
    clear_saved_config,
    describe_config_source,
    read_config_values,
    save_config_values,
)
from ai_subtitle.game_ocr import (
    GalgameOCRTranslator,
    GalgameTranslationEvent,
    GameOCRTranslator,
    ScreenRegion,
)
from ai_subtitle.overlay import OverlayWindow
from ai_subtitle.providers.openai_compatible import OpenAICompatibleProvider
from ai_subtitle.transcribe import resolve_transcription_settings, transcribe_media_to_srt
from ai_subtitle.video_pipeline import translate_srt


class PixelRiderAnimation:
    def __init__(self, master: tk.Misc) -> None:
        self.canvas = tk.Canvas(
            master,
            width=396,
            height=228,
            bg="#f5ead2",
            highlightthickness=0,
            relief="flat",
        )
        self._job: Optional[str] = None
        self._frame_index = 0
        self._pixel = 6
        self._gap = 1
        self._running = False
        self._cycle_index = 0
        self._cycle_length = 160
        self._scene_entities: list[dict[str, float | int | str]] = []
        self._star_positions = (
            (24, 18),
            (58, 34),
            (86, 20),
            (132, 44),
            (166, 24),
            (244, 22),
            (282, 38),
            (316, 18),
            (346, 40),
        )
        self._draw_background()
        self._draw_running_frame(0)

    def pack(self, **kwargs: Any) -> None:
        self.canvas.pack(**kwargs)

    def start(self) -> None:
        self.stop()
        self._running = True
        self._frame_index = 0
        self._tick()

    def show_victory(self) -> None:
        self.stop()
        self._draw_background()
        self._draw_victory_frame()

    def show_rest(self) -> None:
        self.stop()
        self._draw_background()
        self._draw_running_frame(self._frame_index)

    def stop(self) -> None:
        self._running = False
        if self._job is not None:
            try:
                self.canvas.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def destroy(self) -> None:
        self.stop()
        try:
            self.canvas.destroy()
        except tk.TclError:
            pass

    def _tick(self) -> None:
        if not self._running:
            return

        self._advance_scene()
        self._draw_background()
        self._draw_running_frame(self._frame_index)
        self._frame_index = (self._frame_index + 1) % 4
        self._job = self.canvas.after(150, self._tick)

    def _draw_background(self) -> None:
        self.canvas.delete("background")
        light = self._daylight_factor()
        sky_top = self._lerp_color("#13233f", "#f5ead2", light)
        sky_bottom = self._lerp_color("#2f4664", "#efd9aa", light)
        hill = self._lerp_color("#43553b", "#8aa85a", light)
        field = self._lerp_color("#30422f", "#6f8c48", light)
        cloud = self._lerp_color("#7e8da6", "#e3cfae", light)
        text_color = self._lerp_color("#f2e8d5", "#3f3128", light)

        self.canvas.create_rectangle(0, 0, 396, 108, fill=sky_top, outline="", tags="background")
        self.canvas.create_rectangle(0, 108, 396, 148, fill=sky_bottom, outline="", tags="background")
        self.canvas.create_rectangle(0, 148, 396, 228, fill=hill, outline="", tags="background")
        self.canvas.create_rectangle(0, 170, 396, 228, fill=field, outline="", tags="background")

        self._draw_stars(light)

        for x, y in (
            (26, 30),
            (58, 44),
            (94, 24),
            (126, 54),
            (154, 30),
            (274, 36),
            (300, 58),
            (330, 26),
            (352, 44),
        ):
            self._cell(x, y, cloud, "background")
            self._cell(x + 8, y + 8, cloud, "background")

        self._draw_celestial_body(light)
        self._draw_background_entities(light)
        self.canvas.create_text(
            18,
            202,
            text="grassland loading",
            anchor="w",
            fill=text_color,
            font=("Consolas", 10, "bold"),
            tags="background",
        )

    def _draw_running_frame(self, frame: int) -> None:
        self.canvas.delete("sprite")
        bob = (0, 1, 0, 1)[frame]
        horse_x = 88 + (0, 3, 1, -2)[frame]
        horse_y = 76 + bob

        self._draw_horse(horse_x, horse_y, frame, gallop=True)
        self._draw_rider(horse_x + 36, horse_y - 34, frame, victory=False)
        self._draw_dust(horse_x - 28, horse_y + 56, frame)

    def _draw_victory_frame(self) -> None:
        self.canvas.delete("sprite")
        horse_x = 106
        horse_y = 80
        self._draw_horse(horse_x, horse_y, 0, gallop=False)
        self._draw_rider(horse_x + 38, horse_y - 36, 0, victory=True)

        for star_x, star_y in ((270, 42), (292, 28), (314, 48)):
            self._block(star_x, star_y, 2, 1, "#f4c95d", "sprite")
            self._block(star_x + 6, star_y - 6, 1, 2, "#f4c95d", "sprite")

    def _draw_horse(self, x: int, y: int, frame: int, *, gallop: bool) -> None:
        coat = "#f1f0ea"
        shadow = "#d5c9b7"
        outline = "#342821"
        saddle = "#8c5a37"
        bridle = "#6e4630"
        mane = "#c0b2a0"

        self._block(x + 18, y + 16, 17, 5, coat, "sprite")
        self._block(x + 20, y + 21, 13, 3, shadow, "sprite")
        self._block(x + 32, y + 10, 6, 8, coat, "sprite")
        self._block(x + 38, y + 8, 7, 6, coat, "sprite")
        self._block(x + 44, y + 10, 3, 3, shadow, "sprite")
        self._block(x + 33, y + 9, 2, 5, mane, "sprite")
        self._block(x + 28, y + 15, 6, 3, saddle, "sprite")
        self._block(x + 27, y + 18, 8, 2, saddle, "sprite")
        self._block(x + 16, y + 18, 3, 3, outline, "sprite")
        self._block(x + 13, y + 20 + (frame % 2), 3, 4, outline, "sprite")
        self._block(x + 37, y + 13, 6, 1, bridle, "sprite")
        self._block(x + 44, y + 14, 1, 2, outline, "sprite")
        self._block(x + 45, y + 13, 1, 1, outline, "sprite")
        self._block(x + 40, y + 7, 1, 2, outline, "sprite")
        self._block(x + 43, y + 7, 1, 2, outline, "sprite")
        self._block(x + 41, y + 12, 1, 1, outline, "sprite")

        if gallop:
            legs = (
                ((20, 25, 1, 7), (25, 24, 1, 8), (31, 25, 1, 7), (36, 24, 1, 8)),
                ((19, 24, 1, 8), (25, 26, 1, 6), (31, 24, 1, 8), (37, 25, 1, 7)),
                ((20, 25, 1, 7), (26, 24, 1, 8), (30, 26, 1, 6), (36, 24, 1, 8)),
                ((19, 24, 1, 8), (25, 25, 1, 7), (31, 24, 1, 8), (37, 26, 1, 6)),
            )[frame]
        else:
            legs = ((20, 25, 1, 8), (25, 25, 1, 8), (31, 25, 1, 8), (36, 25, 1, 8))

        for leg_x, leg_y, leg_w, leg_h in legs:
            self._block(x + leg_x, y + leg_y, leg_w, leg_h, outline, "sprite")

        self._block(x + 20, y + 32, 1, 1, outline, "sprite")
        self._block(x + 25, y + 32, 1, 1, outline, "sprite")
        self._block(x + 31, y + 32, 1, 1, outline, "sprite")
        self._block(x + 36, y + 32, 1, 1, outline, "sprite")

    def _draw_rider(self, x: int, y: int, frame: int, *, victory: bool) -> None:
        skin = "#e7b08a"
        hair = "#2c2118"
        coat = "#b95739"
        skirt = "#355b7a"
        accent = "#f2ca69"
        scarf = "#2e7280"
        outline = "#2f241f"

        self._block(x + 2, y + 10, 4, 5, coat, "sprite")
        self._block(x + 3, y + 15, 3, 3, skirt, "sprite")
        self._block(x + 3, y + 5, 2, 4, skin, "sprite")
        self._block(x + 2, y + 4, 4, 2, hair, "sprite")
        self._block(x + 1, y + 3, 6, 1, accent, "sprite")
        self._block(x + 2, y + 9, 4, 1, scarf, "sprite")
        self._block(x + 1, y + 6, 1, 4, hair, "sprite")

        if victory:
            self._block(x + 1, y + 10, 1, 6, outline, "sprite")
            self._block(x - 1, y + 6, 1, 5, outline, "sprite")
            self._block(x + 6, y + 10, 1, 6, outline, "sprite")
            self._block(x + 8, y + 5, 1, 5, outline, "sprite")
            self._block(x - 1, y + 4, 1, 1, accent, "sprite")
            self._block(x + 8, y + 3, 1, 1, accent, "sprite")
        else:
            arm_shift = (0, 1, 0, -1)[frame]
            self._block(x + 1, y + 10, 1, 4, outline, "sprite")
            self._block(x + 6, y + 10 + arm_shift, 1, 4, outline, "sprite")
            self._block(x + 7, y + 12 + arm_shift, 1, 1, accent, "sprite")

        self._block(x + 3, y + 18, 1, 3, outline, "sprite")
        self._block(x + 5, y + 18, 1, 3, outline, "sprite")
        self._block(x + 3, y + 21, 1, 1, accent, "sprite")
        self._block(x + 5, y + 21, 1, 1, accent, "sprite")

    def _draw_dust(self, x: int, y: int, frame: int) -> None:
        colors = ("#d5bea1", "#cdae88")
        clouds = (
            ((0, 2), (2, 1), (6, 0)),
            ((1, 1), (4, 0), (7, 2)),
            ((0, 1), (3, 2), (6, 1)),
            ((1, 2), (4, 1), (8, 0)),
        )[frame]
        for idx, (cx, cy) in enumerate(clouds):
            self._block(x + cx * 6, y + cy * 6, 2, 1, colors[idx % 2], "sprite")

    def _advance_scene(self) -> None:
        self._cycle_index = (self._cycle_index + 1) % self._cycle_length
        next_entities: list[dict[str, float | int | str]] = []
        for entity in self._scene_entities:
            entity["x"] = float(entity["x"]) - float(entity["speed"])
            if float(entity["x"]) > -96:
                next_entities.append(entity)
        self._scene_entities = next_entities

        if len(self._scene_entities) >= 3:
            return
        if self._cycle_index % 18 != 0:
            return
        if random.random() > 0.55:
            return

        kind = random.choice(["ger", "sheep", "cattle", "horses"])
        lane = random.choice([0, 1, 2])
        speed = {0: 1.2, 1: 1.6, 2: 2.0}[lane]
        spawn_x = 420 + random.randint(0, 70)
        entity: dict[str, float | int | str] = {
            "kind": kind,
            "x": float(spawn_x),
            "lane": lane,
            "speed": speed,
            "variant": random.randint(0, 2),
        }
        self._scene_entities.append(entity)

    def _daylight_factor(self) -> float:
        phase = self._cycle_index / self._cycle_length
        if phase < 0.5:
            return phase / 0.5
        return (1.0 - phase) / 0.5

    def _draw_stars(self, light: float) -> None:
        if light > 0.45:
            return
        star_color = self._lerp_color("#b6c5df", "#fff3bf", 1.0 - (light / 0.45))
        for x, y in self._star_positions:
            self._cell(x, y, star_color, "background")
            if (x + y + self._frame_index) % 3 == 0:
                self._cell(x + 6, y + 6, star_color, "background")

    def _draw_celestial_body(self, light: float) -> None:
        phase = self._cycle_index / self._cycle_length
        travel = phase if phase < 0.5 else phase - 0.5
        travel *= 2.0

        sun_x = 28 + int(312 * travel)
        sun_y = 78 - int(44 * (1.0 - abs(0.5 - travel) * 2.0))
        moon_x = 28 + int(312 * ((travel + 0.5) % 1.0))
        moon_y = 82 - int(40 * (1.0 - abs(0.5 - ((travel + 0.5) % 1.0)) * 2.0))

        if light >= 0.5:
            self.canvas.create_oval(
                sun_x,
                sun_y,
                sun_x + 44,
                sun_y + 44,
                fill="#f3c86c",
                outline="",
                tags="background",
            )
        else:
            self.canvas.create_oval(
                moon_x,
                moon_y,
                moon_x + 36,
                moon_y + 36,
                fill="#d7dfed",
                outline="",
                tags="background",
            )
            self.canvas.create_oval(
                moon_x + 10,
                moon_y + 4,
                moon_x + 34,
                moon_y + 30,
                fill=self._lerp_color("#13233f", "#2f4664", light),
                outline="",
                tags="background",
            )

    def _draw_background_entities(self, light: float) -> None:
        for entity in sorted(self._scene_entities, key=lambda item: int(item["lane"])):
            lane = int(entity["lane"])
            x = int(float(entity["x"]))
            y = 112 + lane * 18
            if entity["kind"] == "ger":
                self._draw_ger(x, y, light)
            elif entity["kind"] == "sheep":
                self._draw_sheep_group(x, y, light, int(entity["variant"]))
            elif entity["kind"] == "cattle":
                self._draw_cattle_group(x, y, light, int(entity["variant"]))
            else:
                self._draw_horse_group(x, y, light, int(entity["variant"]))

    def _draw_ger(self, x: int, y: int, light: float) -> None:
        felt = self._lerp_color("#6b768c", "#efe1c7", light)
        shadow = self._lerp_color("#4f5668", "#d4b98e", light)
        roof = self._lerp_color("#8a90a3", "#b75c3b", light)
        door = self._lerp_color("#495268", "#82563b", light)
        self._block(x, y + 10, 7, 4, felt, "background")
        self._block(x + 1, y + 8, 5, 2, shadow, "background")
        self._block(x + 2, y + 6, 3, 2, roof, "background")
        self._block(x + 3, y + 11, 1, 3, door, "background")

    def _draw_sheep_group(self, x: int, y: int, light: float, variant: int) -> None:
        fleece = self._lerp_color("#8b95a8", "#f1eee7", light)
        head = self._lerp_color("#4b4b56", "#54453f", light)
        for offset in (0, 16 + variant * 2, 32 + variant * 3):
            self._block(x + offset, y + 8, 3, 2, fleece, "background")
            self._block(x + offset + 2, y + 7, 1, 1, fleece, "background")
            self._block(x + offset + 3, y + 9, 1, 1, head, "background")
            self._block(x + offset + 1, y + 10, 1, 2, head, "background")
            self._block(x + offset + 3, y + 10, 1, 2, head, "background")

    def _draw_cattle_group(self, x: int, y: int, light: float, variant: int) -> None:
        body = self._lerp_color("#515766", "#8c5c42", light)
        horn = self._lerp_color("#b4c0d0", "#d8c39b", light)
        for offset in (0, 22 + variant * 2):
            self._block(x + offset, y + 7, 5, 3, body, "background")
            self._block(x + offset + 5, y + 8, 2, 2, body, "background")
            self._block(x + offset + 6, y + 7, 1, 1, horn, "background")
            self._block(x + offset + 6, y + 10, 1, 2, body, "background")
            self._block(x + offset + 1, y + 10, 1, 2, body, "background")
            self._block(x + offset + 4, y + 10, 1, 2, body, "background")

    def _draw_horse_group(self, x: int, y: int, light: float, variant: int) -> None:
        coat = self._lerp_color("#646f84", "#c9a27b", light)
        mane = self._lerp_color("#323746", "#6e4630", light)
        for offset in (0, 20 + variant * 3):
            self._block(x + offset, y + 8, 5, 2, coat, "background")
            self._block(x + offset + 4, y + 7, 2, 2, coat, "background")
            self._block(x + offset + 3, y + 6, 1, 2, mane, "background")
            self._block(x + offset + 1, y + 10, 1, 3, mane, "background")
            self._block(x + offset + 4, y + 10, 1, 3, mane, "background")

    def _lerp_color(self, start: str, end: str, ratio: float) -> str:
        ratio = max(0.0, min(1.0, ratio))
        start_rgb = self._hex_to_rgb(start)
        end_rgb = self._hex_to_rgb(end)
        blended = tuple(
            int(round(start_value + (end_value - start_value) * ratio))
            for start_value, end_value in zip(start_rgb, end_rgb)
        )
        return self._rgb_to_hex(blended)

    def _hex_to_rgb(self, value: str) -> tuple[int, int, int]:
        value = value.lstrip("#")
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)

    def _rgb_to_hex(self, value: tuple[int, int, int]) -> str:
        return "#{:02x}{:02x}{:02x}".format(*value)

    def _block(self, x: int, y: int, width: int, height: int, color: str, tag: str) -> None:
        for iy in range(height):
            for ix in range(width):
                self._cell(x + ix * self._pixel, y + iy * self._pixel, color, tag)

    def _cell(self, x: int, y: int, color: str, tag: str) -> None:
        self.canvas.create_rectangle(
            x,
            y,
            x + self._pixel - self._gap,
            y + self._pixel - self._gap,
            fill=color,
            outline="",
            tags=tag,
        )


class SubtitleTranslatorGUI:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("AI Subtitle Translator")
        self.root.geometry("1080x760")
        self.root.minsize(980, 680)
        self.root.configure(bg="#f3efe7")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._game_translator: Optional[GameOCRTranslator] = None
        self._overlay: Optional[OverlayWindow] = None
        self._stopping_game_ocr = False
        self._galgame_translator: Optional[GalgameOCRTranslator] = None
        self._galgame_overlay: Optional[OverlayWindow] = None
        self._stopping_galgame_ocr = False

        self.base_url_var = tk.StringVar()
        self.api_key_var = tk.StringVar()
        self.model_var = tk.StringVar()
        self.timeout_var = tk.StringVar(value="60")

        self.srt_input_var = tk.StringVar()
        self.srt_output_var = tk.StringVar()
        self.srt_target_var = tk.StringVar(value="Simplified Chinese")
        self.srt_bilingual_var = tk.BooleanVar(value=True)
        self.srt_batch_var = tk.StringVar(value="20")
        self.video_input_var = tk.StringVar()
        self.video_srt_output_var = tk.StringVar()
        self.video_profile_var = tk.StringVar(value="Balanced")
        self.whisper_model_var = tk.StringVar(value="small")
        self.video_language_var = tk.StringVar(value="auto")
        self.video_device_var = tk.StringVar(value="cpu")
        self.video_compute_type_var = tk.StringVar(value="int8")
        self.video_translate_after_var = tk.BooleanVar(value=False)

        self.game_region_var = tk.StringVar(value="200,780,1520,220")
        self.game_target_var = tk.StringVar(value="Simplified Chinese")
        self.game_interval_var = tk.StringVar(value="0.8")
        self.game_similarity_var = tk.StringVar(value="0.92")
        self.game_min_display_var = tk.StringVar(value="2.2")
        self.game_max_display_var = tk.StringVar(value="5.5")
        self.galgame_dialogue_region_var = tk.StringVar(value="200,780,1520,220")
        self.galgame_name_region_var = tk.StringVar(value="")
        self.galgame_target_var = tk.StringVar(value="Simplified Chinese")
        self.galgame_interval_var = tk.StringVar(value="0.45")
        self.galgame_similarity_var = tk.StringVar(value="0.96")
        self.galgame_stable_passes_var = tk.StringVar(value="2")
        self.galgame_min_chars_var = tk.StringVar(value="2")
        self.galgame_min_display_var = tk.StringVar(value="2.4")
        self.galgame_max_display_var = tk.StringVar(value="7.0")

        self.status_var = tk.StringVar(value="Ready")
        self.config_source_var = tk.StringVar(value="Config source: unresolved")
        self._log_file_path = Path.cwd() / "ai_subtitle.log"
        self._task_active = False
        self._task_window: Optional[tk.Toplevel] = None
        self._task_status_var = tk.StringVar(value="Idle")
        self._task_log_text: Optional[ScrolledText] = None
        self._task_progressbar: Optional[ttk.Progressbar] = None
        self._task_animation: Optional[PixelRiderAnimation] = None
        self._main_canvas: Optional[tk.Canvas] = None
        self._scroll_frame: Optional[ttk.Frame] = None
        self._galgame_history_text: Optional[ScrolledText] = None

        self._configure_style()
        self._build_layout()
        self._load_saved_config()

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("App.TFrame", background="#f3efe7")
        style.configure(
            "Card.TLabelframe",
            background="#f3efe7",
            borderwidth=1,
            relief="solid",
        )
        style.configure(
            "Card.TLabelframe.Label",
            background="#f3efe7",
            foreground="#2f241f",
            font=("Segoe UI Semibold", 11),
        )
        style.configure("App.TLabel", background="#f3efe7", foreground="#2f241f")
        style.configure("Accent.TButton", font=("Segoe UI Semibold", 10))
        style.configure("App.TCheckbutton", background="#f3efe7")
        style.configure("App.TNotebook", background="#f3efe7", borderwidth=0)
        style.configure(
            "App.TNotebook.Tab",
            font=("Segoe UI Semibold", 10),
            padding=(18, 10),
        )

    def _build_layout(self) -> None:
        shell = ttk.Frame(self.root, style="App.TFrame")
        shell.pack(fill="both", expand=True)

        canvas = tk.Canvas(
            shell,
            bg="#f3efe7",
            highlightthickness=0,
            relief="flat",
        )
        scrollbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        outer = ttk.Frame(canvas, padding=18, style="App.TFrame")
        self._main_canvas = canvas
        self._scroll_frame = outer

        canvas_window = canvas.create_window((0, 0), window=outer, anchor="nw")
        outer.bind(
            "<Configure>",
            lambda event: self._on_scroll_frame_configure(),
        )
        canvas.bind(
            "<Configure>",
            lambda event: self._on_canvas_resize(canvas_window),
        )
        canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        header = ttk.Frame(outer, style="App.TFrame")
        header.pack(fill="x")

        title = tk.Label(
            header,
            text="AI Subtitle Translator",
            bg="#f3efe7",
            fg="#1c1714",
            font=("Segoe UI Semibold", 22),
        )
        title.pack(anchor="w")

        subtitle = tk.Label(
            header,
            text="Auto-detect API config when available. Only fill the fields if you want to override them.",
            bg="#f3efe7",
            fg="#5f544e",
            font=("Segoe UI", 10),
        )
        subtitle.pack(anchor="w", pady=(4, 14))

        self._build_api_card(outer)

        notebook = ttk.Notebook(outer, style="App.TNotebook")
        notebook.pack(fill="both", expand=True, pady=(16, 12))

        video_tab = ttk.Frame(notebook, padding=16, style="App.TFrame")
        game_tab = ttk.Frame(notebook, padding=16, style="App.TFrame")
        galgame_tab = ttk.Frame(notebook, padding=16, style="App.TFrame")
        notebook.add(video_tab, text="Video Subtitle")
        notebook.add(galgame_tab, text="Galgame")
        notebook.add(game_tab, text="Game OCR")

        self._build_video_tab(video_tab)
        self._build_galgame_tab(galgame_tab)
        self._build_game_tab(game_tab)

        log_frame = ttk.LabelFrame(outer, text="Activity", padding=12, style="Card.TLabelframe")
        log_frame.pack(fill="both", expand=False)

        self.log_text = ScrolledText(
            log_frame,
            height=10,
            bg="#1f1a17",
            fg="#f7f1eb",
            insertbackground="#f7f1eb",
            relief="flat",
            font=("Consolas", 10),
        )
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")

        status_bar = tk.Label(
            outer,
            textvariable=self.status_var,
            bg="#d8c4a8",
            fg="#2b221d",
            anchor="w",
            padx=12,
            pady=8,
            font=("Segoe UI Semibold", 10),
        )
        status_bar.pack(fill="x")

    def _on_scroll_frame_configure(self) -> None:
        if self._main_canvas is None or self._scroll_frame is None:
            return

        self._main_canvas.configure(scrollregion=self._main_canvas.bbox("all"))

    def _on_canvas_resize(self, canvas_window: int) -> None:
        if self._main_canvas is None:
            return

        width = self._main_canvas.winfo_width()
        self._main_canvas.itemconfigure(canvas_window, width=width)

    def _on_mousewheel(self, event: tk.Event) -> None:
        if self._main_canvas is None:
            return

        delta = 0
        if getattr(event, "delta", 0):
            delta = int(-event.delta / 120)
        if delta:
            self._main_canvas.yview_scroll(delta, "units")

    def _build_api_card(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="API Settings", padding=12, style="Card.TLabelframe")
        frame.pack(fill="x")

        self._add_labeled_entry(frame, "Base URL", self.base_url_var, row=0, width=68)
        self._add_labeled_entry(frame, "API Key", self.api_key_var, row=1, width=68, show="*")
        self._add_labeled_entry(frame, "Model", self.model_var, row=2, width=30)
        self._add_labeled_entry(frame, "Timeout", self.timeout_var, row=2, column=2, width=12)

        actions = ttk.Frame(frame, style="App.TFrame")
        actions.grid(row=3, column=0, columnspan=4, sticky="w", pady=(12, 0))

        ttk.Button(actions, text="Reload Auto", command=self._load_saved_config).pack(side="left")
        ttk.Button(actions, text="Save Override", command=self._save_config).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Clear Override", command=self._clear_saved_override).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Test API", style="Accent.TButton", command=self._test_api).pack(
            side="left",
            padx=(8, 0),
        )
        ttk.Button(actions, text="Open Log", command=self._open_log_file).pack(side="left", padx=(8, 0))

        source_label = tk.Label(
            frame,
            textvariable=self.config_source_var,
            bg="#f3efe7",
            fg="#6c6059",
            font=("Segoe UI", 9),
        )
        source_label.grid(row=4, column=0, columnspan=4, sticky="w", pady=(10, 0))

    def _build_video_tab(self, parent: ttk.Frame) -> None:
        transcribe_frame = ttk.LabelFrame(
            parent,
            text="Transcribe Video Or Audio To SRT",
            padding=12,
            style="Card.TLabelframe",
        )
        transcribe_frame.pack(fill="x", anchor="n")

        self._add_file_row(
            transcribe_frame,
            "Input Video",
            self.video_input_var,
            self._choose_video_input,
            row=0,
            filetypes=[
                ("Media files", "*.mp4;*.mkv;*.avi;*.mov;*.mp3;*.wav;*.m4a;*.flac"),
                ("All files", "*.*"),
            ],
        )
        self._add_file_row(
            transcribe_frame,
            "Output SRT",
            self.video_srt_output_var,
            self._choose_video_srt_output,
            row=1,
            save=True,
            filetypes=[("SRT files", "*.srt"), ("All files", "*.*")],
        )

        video_actions = ttk.Frame(transcribe_frame, style="App.TFrame")
        video_actions.grid(row=2, column=0, columnspan=3, sticky="w", pady=(2, 8))
        ttk.Button(video_actions, text="Play Video", command=self._play_selected_video).pack(side="left")
        ttk.Button(video_actions, text="Open Folder", command=self._open_selected_video_folder).pack(side="left", padx=(8, 0))

        self._add_combo_row(
            transcribe_frame,
            "Recognition Profile",
            self.video_profile_var,
            ["Balanced", "High Quality", "Noisy Scene"],
            row=3,
            width=18,
        )
        self._add_combo_row(
            transcribe_frame,
            "Whisper Model",
            self.whisper_model_var,
            ["tiny", "base", "small", "medium", "large-v3"],
            row=4,
            width=16,
        )
        self._add_labeled_entry(transcribe_frame, "Speech Language", self.video_language_var, row=4, column=2, width=16)
        self._add_combo_row(
            transcribe_frame,
            "Device",
            self.video_device_var,
            ["auto", "cpu", "cuda"],
            row=5,
            width=12,
        )
        self._add_combo_row(
            transcribe_frame,
            "Compute Type",
            self.video_compute_type_var,
            ["int8", "int8_float16", "float16", "float32"],
            row=5,
            column=2,
            width=16,
        )

        ttk.Checkbutton(
            transcribe_frame,
            text="Translate generated SRT right after transcription",
            variable=self.video_translate_after_var,
            style="App.TCheckbutton",
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 0))

        ttk.Button(
            transcribe_frame,
            text="Generate Subtitle From Video",
            style="Accent.TButton",
            command=self._start_video_transcription,
        ).grid(row=7, column=0, sticky="w", pady=(14, 0))

        frame = ttk.LabelFrame(parent, text="Translate Existing SRT", padding=12, style="Card.TLabelframe")
        frame.pack(fill="x", anchor="n", pady=(16, 0))

        self._add_file_row(frame, "Input SRT", self.srt_input_var, self._choose_srt_input, row=0)
        self._add_file_row(frame, "Output SRT", self.srt_output_var, self._choose_srt_output, row=1, save=True)
        self._add_labeled_entry(frame, "Target Language", self.srt_target_var, row=2, width=24)
        self._add_labeled_entry(frame, "Batch Size", self.srt_batch_var, row=2, column=2, width=12)

        ttk.Checkbutton(
            frame,
            text="Keep original text and translation together",
            variable=self.srt_bilingual_var,
            style="App.TCheckbutton",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(10, 0))

        ttk.Button(
            frame,
            text="Start Translation",
            style="Accent.TButton",
            command=self._start_srt_translation,
        ).grid(row=4, column=0, sticky="w", pady=(14, 0))

        hint = tk.Label(
            parent,
            text="Recognition Profile: Balanced for normal use, High Quality for cleaner audio, Noisy Scene for crowded or messy audio.",
            bg="#f3efe7",
            fg="#6c6059",
            font=("Segoe UI", 10),
        )
        hint.pack(anchor="w", pady=(12, 0))

    def _build_game_tab(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Live Game OCR Translation", padding=12, style="Card.TLabelframe")
        frame.pack(fill="x", anchor="n")

        self._add_labeled_entry(frame, "Subtitle Region", self.game_region_var, row=0, width=28)
        self._add_labeled_entry(frame, "Target Language", self.game_target_var, row=0, column=2, width=18)
        self._add_labeled_entry(frame, "Interval", self.game_interval_var, row=1, width=10)
        self._add_labeled_entry(frame, "Similarity", self.game_similarity_var, row=1, column=2, width=10)
        self._add_labeled_entry(frame, "Min Display", self.game_min_display_var, row=2, width=10)
        self._add_labeled_entry(frame, "Max Display", self.game_max_display_var, row=2, column=2, width=10)

        tip = tk.Label(
            frame,
            text="Region format: left,top,width,height. Subtitle stays on screen for an auto-calculated time between Min Display and Max Display.",
            bg="#f3efe7",
            fg="#6c6059",
            font=("Segoe UI", 10),
        )
        tip.grid(row=3, column=0, columnspan=4, sticky="w", pady=(10, 0))

        actions = ttk.Frame(frame, style="App.TFrame")
        actions.grid(row=4, column=0, columnspan=4, sticky="w", pady=(14, 0))
        ttk.Button(actions, text="Start OCR", style="Accent.TButton", command=self._start_game_ocr).pack(side="left")
        ttk.Button(actions, text="Stop OCR", command=self._stop_game_ocr).pack(side="left", padx=(8, 0))

    def _build_galgame_tab(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Galgame Real-Time OCR Translation", padding=12, style="Card.TLabelframe")
        frame.pack(fill="x", anchor="n")

        self._add_labeled_entry(frame, "Dialogue Region", self.galgame_dialogue_region_var, row=0, width=28)
        self._add_labeled_entry(frame, "Name Region", self.galgame_name_region_var, row=0, column=2, width=24)
        self._add_labeled_entry(frame, "Target Language", self.galgame_target_var, row=1, width=18)
        self._add_labeled_entry(frame, "Interval", self.galgame_interval_var, row=1, column=2, width=10)
        self._add_labeled_entry(frame, "Similarity", self.galgame_similarity_var, row=2, width=10)
        self._add_labeled_entry(frame, "Stable Passes", self.galgame_stable_passes_var, row=2, column=2, width=10)
        self._add_labeled_entry(frame, "Min Chars", self.galgame_min_chars_var, row=3, width=10)
        self._add_labeled_entry(frame, "Min Display", self.galgame_min_display_var, row=3, column=2, width=10)
        self._add_labeled_entry(frame, "Max Display", self.galgame_max_display_var, row=4, width=10)

        tip = tk.Label(
            frame,
            text=(
                "Dialogue Region is required. Name Region is optional. "
                "Stable Passes waits for the same line to stay visible before translation, "
                "which works better for letter-by-letter galgame text."
            ),
            bg="#f3efe7",
            fg="#6c6059",
            font=("Segoe UI", 10),
            wraplength=900,
            justify="left",
        )
        tip.grid(row=5, column=0, columnspan=4, sticky="w", pady=(10, 0))

        actions = ttk.Frame(frame, style="App.TFrame")
        actions.grid(row=6, column=0, columnspan=4, sticky="w", pady=(14, 0))
        ttk.Button(actions, text="Start Galgame OCR", style="Accent.TButton", command=self._start_galgame_ocr).pack(side="left")
        ttk.Button(actions, text="Stop Galgame OCR", command=self._stop_galgame_ocr).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Clear History", command=self._clear_galgame_history).pack(side="left", padx=(8, 0))

        history_frame = ttk.LabelFrame(parent, text="Galgame History", padding=12, style="Card.TLabelframe")
        history_frame.pack(fill="both", expand=True, anchor="n", pady=(16, 0))

        self._galgame_history_text = ScrolledText(
            history_frame,
            height=16,
            bg="#1f1a17",
            fg="#f7f1eb",
            insertbackground="#f7f1eb",
            relief="flat",
            font=("Consolas", 10),
        )
        self._galgame_history_text.pack(fill="both", expand=True)
        self._galgame_history_text.configure(state="disabled")

    def _add_labeled_entry(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        *,
        row: int,
        column: int = 0,
        width: int = 24,
        show: Optional[str] = None,
    ) -> None:
        ttk.Label(parent, text=label, style="App.TLabel").grid(
            row=row,
            column=column,
            sticky="w",
            pady=6,
        )
        entry = ttk.Entry(parent, textvariable=variable, width=width, show=show)
        entry.grid(row=row, column=column + 1, sticky="we", padx=(10, 18), pady=6)
        parent.grid_columnconfigure(column + 1, weight=1)

    def _add_file_row(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        command: Callable[[], None],
        *,
        row: int,
        save: bool = False,
        filetypes=None,
    ) -> None:
        ttk.Label(parent, text=label, style="App.TLabel").grid(row=row, column=0, sticky="w", pady=6)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="we", padx=(10, 10), pady=6)
        parent.grid_columnconfigure(1, weight=1)
        button_label = "Save As..." if save else "Browse..."
        ttk.Button(parent, text=button_label, command=command).grid(row=row, column=2, sticky="w", pady=6)

    def _add_combo_row(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        values: list[str],
        *,
        row: int,
        column: int = 0,
        width: int = 16,
    ) -> None:
        ttk.Label(parent, text=label, style="App.TLabel").grid(
            row=row,
            column=column,
            sticky="w",
            pady=6,
        )
        combo = ttk.Combobox(
            parent,
            textvariable=variable,
            values=values,
            width=width,
            state="readonly",
        )
        combo.grid(row=row, column=column + 1, sticky="we", padx=(10, 18), pady=6)
        parent.grid_columnconfigure(column + 1, weight=1)

    def _load_saved_config(self) -> None:
        values = read_config_values()
        self.base_url_var.set(values["LLM_BASE_URL"])
        self.api_key_var.set(values["LLM_API_KEY"])
        self.model_var.set(values["LLM_MODEL"])
        self.timeout_var.set(values["LLM_TIMEOUT"] or "60")
        source_description = describe_config_source(values)
        self.config_source_var.set(f"Config source: {source_description}")
        self._set_status("API settings loaded")
        self._log(f"Loaded API settings. {source_description}")

    def _save_config(self) -> None:
        try:
            config = self._build_config_from_form()
            save_config_values(
                base_url=config.base_url,
                api_key=config.api_key,
                model=config.model,
                timeout=config.timeout,
            )
        except Exception as exc:
            self._show_error("Save failed", str(exc))
            return

        self._load_saved_config()
        self._set_status("Custom API override saved to .env")
        self._log("Saved custom API override to .env")

    def _clear_saved_override(self) -> None:
        try:
            clear_saved_config()
        except Exception as exc:
            self._show_error("Clear override failed", str(exc))
            return

        self._load_saved_config()
        self._set_status("Custom API override cleared")
        self._log("Cleared custom API override. Using automatic config resolution.")

    def _test_api(self) -> None:
        config = self._build_config_from_form()
        self._run_in_background(
            "Testing API...",
            lambda: self._test_api_worker(config),
        )

    def _test_api_worker(self, config) -> None:
        provider = OpenAICompatibleProvider(config)
        translated = provider.translate_lines(
            ["Hello, traveler."],
            target_language="Simplified Chinese",
            context_hint="Short connectivity test.",
        )[0]
        self._log_from_thread(f"API test ok: {translated}")
        self._set_status_from_thread("API test succeeded")

    def _choose_srt_input(self) -> None:
        selected = filedialog.askopenfilename(
            title="Choose subtitle file",
            filetypes=[("SRT files", "*.srt"), ("All files", "*.*")],
        )
        if not selected:
            return

        self.srt_input_var.set(selected)
        input_path = Path(selected)
        default_output = input_path.with_name(f"{input_path.stem}.translated{input_path.suffix}")
        self.srt_output_var.set(str(default_output))

    def _choose_video_input(self) -> None:
        selected = filedialog.askopenfilename(
            title="Choose video or audio file",
            filetypes=[
                ("Media files", "*.mp4;*.mkv;*.avi;*.mov;*.mp3;*.wav;*.m4a;*.flac"),
                ("All files", "*.*"),
            ],
        )
        if not selected:
            return

        self.video_input_var.set(selected)
        input_path = Path(selected)
        srt_path = input_path.with_suffix(".srt")
        self.video_srt_output_var.set(str(srt_path))
        self.srt_input_var.set(str(srt_path))
        self.srt_output_var.set(str(input_path.with_name(f"{input_path.stem}.translated.srt")))

    def _choose_video_srt_output(self) -> None:
        selected = filedialog.asksaveasfilename(
            title="Choose transcription SRT output",
            defaultextension=".srt",
            filetypes=[("SRT files", "*.srt"), ("All files", "*.*")],
        )
        if selected:
            self.video_srt_output_var.set(selected)

    def _play_selected_video(self) -> None:
        video_path = self.video_input_var.get().strip()
        if not video_path:
            self._show_error("No video selected", "Choose a video or audio file first.")
            return

        path_obj = Path(video_path)
        if not path_obj.exists():
            self._show_error("File not found", f"Selected media file does not exist:\n{video_path}")
            return

        try:
            os.startfile(str(path_obj))
        except Exception as exc:
            self._show_error("Play failed", str(exc))

    def _open_selected_video_folder(self) -> None:
        video_path = self.video_input_var.get().strip()
        if not video_path:
            self._show_error("No video selected", "Choose a video or audio file first.")
            return

        path_obj = Path(video_path)
        if not path_obj.exists():
            self._show_error("File not found", f"Selected media file does not exist:\n{video_path}")
            return

        try:
            os.startfile(str(path_obj.parent))
        except Exception as exc:
            self._show_error("Open folder failed", str(exc))

    def _choose_srt_output(self) -> None:
        selected = filedialog.asksaveasfilename(
            title="Choose output subtitle file",
            defaultextension=".srt",
            filetypes=[("SRT files", "*.srt"), ("All files", "*.*")],
        )
        if selected:
            self.srt_output_var.set(selected)

    def _start_srt_translation(self) -> None:
        request = self._get_srt_translation_request()
        self._run_in_background(
            "Translating subtitle file...",
            lambda: self._translate_srt_worker(request),
        )

    def _start_video_transcription(self) -> None:
        self._log("Start transcription requested.")
        request = self._get_transcription_request()
        self._run_in_background(
            "Transcribing media into subtitle...",
            lambda: self._transcribe_video_worker(request),
        )

    def _translate_srt_worker(self, request: Dict[str, Any]) -> None:
        input_path = request["input_path"]
        output_path = request["output_path"]
        if not input_path:
            raise ValueError("Choose an input SRT file first.")
        if not output_path:
            raise ValueError("Choose an output SRT path first.")

        provider = OpenAICompatibleProvider(request["config"])
        translate_srt(
            input_path,
            output_path,
            provider=provider,
            target_language=request["target_language"],
            bilingual=request["bilingual"],
            batch_size=request["batch_size"],
        )
        self._log_from_thread(f"SRT translation finished: {output_path}")
        self._set_status_from_thread("Subtitle translation finished")

    def _transcribe_video_worker(self, request: Dict[str, Any]) -> None:
        input_path = request["input_path"]
        output_path = request["output_path"]
        if not input_path:
            raise ValueError("Choose a video or audio file first.")
        if not output_path:
            raise ValueError("Choose an output SRT path first.")

        self._log_from_thread(
            "Recognition settings: "
            f"profile={request['profile']}, "
            f"model={request['model_size']}, "
            f"beam={request['beam_size']}, "
            f"vad={'on' if request['vad_filter'] else 'off'}, "
            f"audio_cleanup={'on' if request['preprocess_audio'] else 'off'}"
        )

        result = transcribe_media_to_srt(
            input_path,
            output_path,
            model_size=request["model_size"],
            language=request["language"],
            device=request["device"],
            compute_type=request["compute_type"],
            beam_size=request["beam_size"],
            vad_filter=request["vad_filter"],
            preprocess_audio=request["preprocess_audio"],
            status_callback=self._progress_from_worker,
        )

        source_path = Path(output_path)
        translated_output = str(source_path.with_name(f"{source_path.stem}.translated{source_path.suffix}"))
        self._set_stringvar_from_thread(self.srt_input_var, output_path)
        self._set_stringvar_from_thread(self.srt_output_var, translated_output)

        self._log_from_thread(
            "Transcription finished: "
            f"{output_path} "
            f"(language={result.detected_language}, segments={result.segment_count})"
        )

        if request["translate_after"]:
            provider = OpenAICompatibleProvider(request["config"])
            translate_srt(
                output_path,
                translated_output,
                provider=provider,
                target_language=request["target_language"],
                bilingual=request["bilingual"],
                batch_size=request["batch_size"],
            )
            self._log_from_thread(f"Auto-translation finished: {translated_output}")
            self._set_status_from_thread("Transcription and translation finished")
            return

        self._set_status_from_thread("Transcription finished")

    def _start_game_ocr(self) -> None:
        if self._galgame_translator is not None and self._galgame_translator.is_running:
            self._show_error("Galgame OCR already running", "Stop the current galgame OCR session first.")
            return
        if self._game_translator is not None and self._game_translator.is_running:
            self._show_error("OCR already running", "Stop the current OCR session before starting a new one.")
            return

        try:
            provider = OpenAICompatibleProvider(self._build_config_from_form())
            region = self._parse_region(self.game_region_var.get().strip())
            interval = float(self.game_interval_var.get().strip())
            similarity = float(self.game_similarity_var.get().strip())
            min_display = float(self.game_min_display_var.get().strip())
            max_display = float(self.game_max_display_var.get().strip())
            if min_display <= 0 or max_display <= 0:
                raise ValueError("Display duration values must be positive.")
            if min_display > max_display:
                raise ValueError("Min Display cannot be greater than Max Display.")

            self._overlay = OverlayWindow(self.root, on_close=self._handle_overlay_close)
            self._game_translator = GameOCRTranslator(
                provider=provider,
                target_language=self.game_target_var.get().strip() or "Simplified Chinese",
                region=region,
                interval_seconds=interval,
                similarity_threshold=similarity,
                min_display_seconds=min_display,
                max_display_seconds=max_display,
            )
            self._game_translator.start(self._overlay)
        except Exception as exc:
            self._cleanup_game_ocr()
            self._show_error("Failed to start OCR", str(exc))
            return

        self._set_status("Game OCR is running")
        self._log("Game OCR started")

    def _stop_game_ocr(self) -> None:
        if self._game_translator is None and self._overlay is None:
            return

        self._stopping_game_ocr = True
        try:
            if self._game_translator is not None:
                self._game_translator.stop()
            if self._overlay is not None:
                self._overlay.close()
        finally:
            self._cleanup_game_ocr()
            self._stopping_game_ocr = False
        self._set_status("Game OCR stopped")
        self._log("Game OCR stopped")

    def _start_galgame_ocr(self) -> None:
        if self._game_translator is not None and self._game_translator.is_running:
            self._show_error("Game OCR already running", "Stop the current game OCR session first.")
            return
        if self._galgame_translator is not None and self._galgame_translator.is_running:
            self._show_error("Galgame OCR already running", "Stop the current galgame OCR session first.")
            return

        try:
            provider = OpenAICompatibleProvider(self._build_config_from_form())
            dialogue_region = self._parse_region(self.galgame_dialogue_region_var.get().strip())
            name_region_text = self.galgame_name_region_var.get().strip()
            name_region = self._parse_region(name_region_text) if name_region_text else None
            interval = float(self.galgame_interval_var.get().strip())
            similarity = float(self.galgame_similarity_var.get().strip())
            stable_passes = int(self.galgame_stable_passes_var.get().strip())
            min_chars = int(self.galgame_min_chars_var.get().strip())
            min_display = float(self.galgame_min_display_var.get().strip())
            max_display = float(self.galgame_max_display_var.get().strip())
            if stable_passes <= 0:
                raise ValueError("Stable Passes must be greater than 0.")
            if min_chars <= 0:
                raise ValueError("Min Chars must be greater than 0.")
            if min_display <= 0 or max_display <= 0:
                raise ValueError("Display duration values must be positive.")
            if min_display > max_display:
                raise ValueError("Min Display cannot be greater than Max Display.")

            self._galgame_overlay = OverlayWindow(self.root, on_close=self._handle_galgame_overlay_close)
            self._galgame_translator = GalgameOCRTranslator(
                provider=provider,
                target_language=self.galgame_target_var.get().strip() or "Simplified Chinese",
                dialogue_region=dialogue_region,
                name_region=name_region,
                interval_seconds=interval,
                similarity_threshold=similarity,
                stable_passes=stable_passes,
                min_chars=min_chars,
                min_display_seconds=min_display,
                max_display_seconds=max_display,
                status_callback=self._log_galgame_status_from_thread,
                result_callback=self._handle_galgame_event_from_thread,
            )
            self._galgame_translator.start(self._galgame_overlay)
        except Exception as exc:
            self._cleanup_galgame_ocr()
            self._show_error("Failed to start galgame OCR", str(exc))
            return

        self._set_status("Galgame OCR is running")
        self._log("Galgame OCR started")

    def _stop_galgame_ocr(self) -> None:
        if self._galgame_translator is None and self._galgame_overlay is None:
            return

        self._stopping_galgame_ocr = True
        try:
            if self._galgame_translator is not None:
                self._galgame_translator.stop()
            if self._galgame_overlay is not None:
                self._galgame_overlay.close()
        finally:
            self._cleanup_galgame_ocr()
            self._stopping_galgame_ocr = False
        self._set_status("Galgame OCR stopped")
        self._log("Galgame OCR stopped")

    def _handle_galgame_overlay_close(self) -> None:
        if self._stopping_galgame_ocr:
            return
        self._stop_galgame_ocr()

    def _handle_overlay_close(self) -> None:
        if self._stopping_game_ocr:
            return
        self._stop_game_ocr()

    def _cleanup_game_ocr(self) -> None:
        self._game_translator = None
        self._overlay = None

    def _cleanup_galgame_ocr(self) -> None:
        self._galgame_translator = None
        self._galgame_overlay = None

    def _log_galgame_status_from_thread(self, message: str) -> None:
        self.root.after(0, lambda: self._log(f"[Galgame] {message}"))

    def _handle_galgame_event_from_thread(self, event: GalgameTranslationEvent) -> None:
        self.root.after(0, lambda: self._append_galgame_history(event))

    def _append_galgame_history(self, event: GalgameTranslationEvent) -> None:
        if self._galgame_history_text is None:
            return

        header = "[cached]" if event.cached else "[new]"
        lines = [header]
        if event.speaker:
            lines.append(f"Name: {event.speaker}")
        lines.append("Source:")
        lines.append(event.source_text)
        lines.append("Translation:")
        lines.append(event.translated_text)
        lines.append("")
        block = "\n".join(lines)

        self._galgame_history_text.configure(state="normal")
        self._galgame_history_text.insert("end", block + "\n")
        self._galgame_history_text.see("end")
        self._galgame_history_text.configure(state="disabled")
        self._log(
            "Galgame history updated"
            + (f" for {event.speaker}" if event.speaker else "")
            + (" (cache hit)" if event.cached else "")
        )

    def _clear_galgame_history(self) -> None:
        if self._galgame_history_text is None:
            return
        self._galgame_history_text.configure(state="normal")
        self._galgame_history_text.delete("1.0", "end")
        self._galgame_history_text.configure(state="disabled")
        self._log("Galgame history cleared")

    def _build_config_from_form(self):
        return build_config(
            base_url=self.base_url_var.get(),
            api_key=self.api_key_var.get(),
            model=self.model_var.get(),
            timeout=self.timeout_var.get() or "60",
        )

    def _get_srt_translation_request(self) -> Dict[str, Any]:
        return {
            "config": self._build_config_from_form(),
            "input_path": self.srt_input_var.get().strip(),
            "output_path": self.srt_output_var.get().strip(),
            "target_language": self.srt_target_var.get().strip() or "Simplified Chinese",
            "bilingual": self.srt_bilingual_var.get(),
            "batch_size": int(self.srt_batch_var.get().strip() or "20"),
        }

    def _get_transcription_request(self) -> Dict[str, Any]:
        profile_label = self.video_profile_var.get().strip().lower().replace(" ", "_")
        settings = resolve_transcription_settings(
            model_size=self.whisper_model_var.get().strip() or "small",
            profile=profile_label,
        )
        return {
            "config": self._build_config_from_form(),
            "input_path": self.video_input_var.get().strip(),
            "output_path": self.video_srt_output_var.get().strip(),
            "profile": settings.profile,
            "model_size": settings.model_size,
            "language": self.video_language_var.get().strip() or "auto",
            "device": self.video_device_var.get().strip() or "auto",
            "compute_type": self.video_compute_type_var.get().strip() or "int8",
            "beam_size": settings.beam_size,
            "vad_filter": settings.vad_filter,
            "preprocess_audio": settings.preprocess_audio,
            "translate_after": self.video_translate_after_var.get(),
            "target_language": self.srt_target_var.get().strip() or "Simplified Chinese",
            "bilingual": self.srt_bilingual_var.get(),
            "batch_size": int(self.srt_batch_var.get().strip() or "20"),
        }

    def _parse_region(self, value: str) -> ScreenRegion:
        parts = [part.strip() for part in value.split(",")]
        if len(parts) != 4:
            raise ValueError("Region must be left,top,width,height.")
        left, top, width, height = [int(part) for part in parts]
        return ScreenRegion(left=left, top=top, width=width, height=height)

    def _run_in_background(self, status: str, worker: Callable[[], None]) -> None:
        if self._task_active:
            self._show_error("Task already running", "Wait for the current task to finish first.")
            return

        self._task_active = True
        self._set_status(status)
        self._log(status)
        self._show_task_window(status)

        def runner() -> None:
            try:
                worker()
                self.root.after(0, lambda: self._finish_task_window(True, "Task finished"))
            except Exception as exc:
                error_message = str(exc) or exc.__class__.__name__
                traceback_text = traceback.format_exc()
                self.root.after(0, lambda: self._log(traceback_text.strip()))
                self.root.after(0, lambda: self._finish_task_window(False, error_message))
                self.root.after(0, lambda: self._show_error("Task failed", error_message))

        threading.Thread(target=runner, daemon=True).start()

    def _log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        if self._task_log_text is not None:
            self._task_log_text.configure(state="normal")
            self._task_log_text.insert("end", message + "\n")
            self._task_log_text.see("end")
            self._task_log_text.configure(state="disabled")
        try:
            with self._log_file_path.open("a", encoding="utf-8") as handle:
                handle.write(message + "\n")
        except OSError:
            pass

    def _log_from_thread(self, message: str) -> None:
        self.root.after(0, lambda: self._log(message))

    def _progress_from_worker(self, message: str) -> None:
        self.root.after(0, lambda: self._set_status(message))
        self.root.after(0, lambda: self._log(message))

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)
        if self._task_window is not None:
            self._task_status_var.set(message)

    def _set_status_from_thread(self, message: str) -> None:
        self.root.after(0, lambda: self._set_status(message))

    def _set_stringvar_from_thread(self, variable: tk.StringVar, value: str) -> None:
        self.root.after(0, lambda: variable.set(value))

    def _show_error(self, title: str, message: str) -> None:
        self._set_status(message)
        self._log(message)
        messagebox.showerror(title, message)

    def _open_log_file(self) -> None:
        self._log_file_path.touch(exist_ok=True)
        try:
            os.startfile(str(self._log_file_path))
        except Exception as exc:
            self._show_error("Open log failed", str(exc))

    def _show_task_window(self, initial_status: str) -> None:
        if self._task_window is not None:
            try:
                self._task_window.destroy()
            except tk.TclError:
                pass
        self._task_window = None
        self._task_log_text = None
        self._task_progressbar = None
        if self._task_animation is not None:
            self._task_animation.destroy()
            self._task_animation = None

        self._task_window = tk.Toplevel(self.root)
        self._task_window.title("Task Progress")
        self._task_window.geometry("780x650+220+120")
        self._task_window.minsize(720, 560)
        self._task_window.configure(bg="#f3efe7")
        self._task_window.transient(self.root)
        self._task_window.attributes("-topmost", True)
        self._task_window.protocol("WM_DELETE_WINDOW", self._hide_task_window)

        container = ttk.Frame(self._task_window, padding=14, style="App.TFrame")
        container.pack(fill="both", expand=True)

        title = tk.Label(
            container,
            text="Task In Progress",
            bg="#f3efe7",
            fg="#1c1714",
            font=("Segoe UI Semibold", 15),
        )
        title.pack(anchor="w")

        subtitle = tk.Label(
            container,
            textvariable=self._task_status_var,
            bg="#f3efe7",
            fg="#5f544e",
            font=("Segoe UI", 10),
        )
        subtitle.pack(anchor="w", pady=(4, 12))

        self._task_animation = PixelRiderAnimation(container)
        self._task_animation.pack(fill="x", pady=(0, 12))
        self._task_animation.start()

        self._task_status_var.set(initial_status)
        self._task_progressbar = ttk.Progressbar(container, mode="indeterminate")
        self._task_progressbar.pack(fill="x")
        self._task_progressbar.start(10)

        self._task_log_text = ScrolledText(
            container,
            height=16,
            bg="#1f1a17",
            fg="#f7f1eb",
            insertbackground="#f7f1eb",
            relief="flat",
            font=("Consolas", 10),
        )
        self._task_log_text.pack(fill="both", expand=True, pady=(12, 0))
        self._task_log_text.configure(state="disabled")

        actions = ttk.Frame(container, style="App.TFrame")
        actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="Open Full Log", command=self._open_log_file).pack(side="left")
        ttk.Button(actions, text="Hide", command=self._hide_task_window).pack(side="right")

    def _hide_task_window(self) -> None:
        if self._task_window is None:
            return
        try:
            self._task_window.withdraw()
        except tk.TclError:
            pass

    def _finish_task_window(self, success: bool, message: str) -> None:
        self._task_active = False
        self._set_status(message)
        if self._task_progressbar is not None:
            try:
                self._task_progressbar.stop()
            except tk.TclError:
                pass
        if self._task_animation is not None:
            if success:
                self._task_animation.show_victory()
            else:
                self._task_animation.show_rest()
        if self._task_window is not None:
            try:
                self._task_window.deiconify()
                self._task_window.lift()
            except tk.TclError:
                pass
        if success:
            self._log("Task finished.")
        else:
            self._log("Task failed.")

    def _on_close(self) -> None:
        if self._galgame_translator is not None and self._galgame_translator.is_running:
            self._stop_galgame_ocr()
        if self._game_translator is not None and self._game_translator.is_running:
            self._stop_game_ocr()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    app = SubtitleTranslatorGUI()
    app.run()
    return 0
