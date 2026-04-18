from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable, Optional

from mss import mss
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

from ai_subtitle.overlay import OverlayWindow
from ai_subtitle.providers.base import TranslationProvider


@dataclass
class ScreenRegion:
    left: int
    top: int
    width: int
    height: int


@dataclass
class GalgameTranslationEvent:
    speaker: str
    source_text: str
    translated_text: str
    cached: bool


class GameOCRTranslator:
    def __init__(
        self,
        *,
        provider: TranslationProvider,
        target_language: str,
        region: ScreenRegion,
        interval_seconds: float = 0.8,
        similarity_threshold: float = 0.92,
        min_display_seconds: float = 2.2,
        max_display_seconds: float = 5.5,
    ) -> None:
        self._provider = provider
        self._target_language = target_language
        self._region = region
        self._interval_seconds = interval_seconds
        self._similarity_threshold = similarity_threshold
        self._min_display_seconds = min_display_seconds
        self._max_display_seconds = max_display_seconds
        self._ocr = RapidOCR()
        self._last_source_text = ""
        self._active_overlay_text = ""
        self._display_deadline: Optional[float] = None
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None

    def run(self) -> None:
        overlay = OverlayWindow()
        self.start(overlay)
        try:
            overlay.run()
        finally:
            self.stop()

    def start(self, overlay: OverlayWindow) -> None:
        if self.is_running:
            raise RuntimeError("Game OCR translator is already running.")

        self._stop_event.clear()
        self._worker = threading.Thread(
            target=self._capture_loop,
            args=(overlay,),
            daemon=True,
        )
        self._worker.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._worker is not None and self._worker.is_alive():
            self._worker.join(timeout=1.5)
        self._worker = None

    @property
    def is_running(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _capture_loop(self, overlay: OverlayWindow) -> None:
        with mss() as sct:
            while not self._stop_event.is_set():
                self._maybe_clear_overlay(overlay)
                try:
                    screenshot = sct.grab(
                        {
                            "left": self._region.left,
                            "top": self._region.top,
                            "width": self._region.width,
                            "height": self._region.height,
                        }
                    )
                    image = Image.frombytes(
                        "RGB",
                        screenshot.size,
                        screenshot.rgb,
                    )

                    source_text = self._extract_text(image)
                    if not source_text:
                        if self._wait_for_next_tick():
                            break
                        continue

                    if self._is_similar_to_last(source_text):
                        if self._wait_for_next_tick():
                            break
                        continue

                    self._last_source_text = source_text
                    translated = self._provider.translate_lines(
                        [source_text],
                        target_language=self._target_language,
                        context_hint="Game subtitle translation. Keep it short enough for real-time reading.",
                    )[0]
                    overlay.set_text(translated)
                    self._active_overlay_text = translated
                    self._display_deadline = (
                        time.monotonic() + self._compute_display_seconds(translated)
                    )
                except Exception as exc:
                    error_text = f"OCR error: {exc}"
                    overlay.set_text(error_text)
                    self._active_overlay_text = error_text
                    self._display_deadline = time.monotonic() + self._min_display_seconds

                if self._wait_for_next_tick():
                    break

    def _extract_text(self, image: Image.Image) -> str:
        result, _ = self._ocr(image)
        if not result:
            return ""

        lines: list[str] = []
        for item in result:
            if len(item) < 2:
                continue
            text = str(item[1]).strip()
            if text:
                lines.append(text)

        return "\n".join(lines).strip()

    def _is_similar_to_last(self, current_text: str) -> bool:
        if not self._last_source_text:
            return False

        similarity = SequenceMatcher(
            a=self._last_source_text,
            b=current_text,
        ).ratio()
        return similarity >= self._similarity_threshold

    def _wait_for_next_tick(self) -> bool:
        return self._stop_event.wait(self._interval_seconds)

    def _maybe_clear_overlay(self, overlay: OverlayWindow) -> None:
        if not self._active_overlay_text or self._display_deadline is None:
            return

        if time.monotonic() < self._display_deadline:
            return

        overlay.clear_text()
        self._active_overlay_text = ""
        self._display_deadline = None

    def _compute_display_seconds(self, text: str) -> float:
        readable_text = "".join(text.split())
        if not readable_text:
            return self._min_display_seconds

        estimated = 1.4 + (len(readable_text) / 7.5)
        return max(
            self._min_display_seconds,
            min(self._max_display_seconds, estimated),
        )


class GalgameOCRTranslator:
    def __init__(
        self,
        *,
        provider: TranslationProvider,
        target_language: str,
        dialogue_region: ScreenRegion,
        name_region: Optional[ScreenRegion] = None,
        interval_seconds: float = 0.45,
        similarity_threshold: float = 0.96,
        stable_passes: int = 2,
        min_chars: int = 2,
        min_display_seconds: float = 2.4,
        max_display_seconds: float = 7.0,
        status_callback: Optional[Callable[[str], None]] = None,
        result_callback: Optional[Callable[[GalgameTranslationEvent], None]] = None,
    ) -> None:
        self._provider = provider
        self._target_language = target_language
        self._dialogue_region = dialogue_region
        self._name_region = name_region
        self._interval_seconds = interval_seconds
        self._similarity_threshold = similarity_threshold
        self._stable_passes = max(1, stable_passes)
        self._min_chars = max(1, min_chars)
        self._min_display_seconds = min_display_seconds
        self._max_display_seconds = max_display_seconds
        self._status_callback = status_callback
        self._result_callback = result_callback
        self._ocr = RapidOCR()
        self._translation_cache: dict[tuple[str, str], str] = {}
        self._last_committed_signature = ""
        self._candidate_signature = ""
        self._candidate_speaker = ""
        self._candidate_text = ""
        self._candidate_hits = 0
        self._active_overlay_text = ""
        self._display_deadline: Optional[float] = None
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None

    def start(self, overlay: OverlayWindow) -> None:
        if self.is_running:
            raise RuntimeError("Galgame OCR translator is already running.")

        self._stop_event.clear()
        self._worker = threading.Thread(
            target=self._capture_loop,
            args=(overlay,),
            daemon=True,
        )
        self._worker.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._worker is not None and self._worker.is_alive():
            self._worker.join(timeout=1.5)
        self._worker = None

    @property
    def is_running(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _capture_loop(self, overlay: OverlayWindow) -> None:
        with mss() as sct:
            while not self._stop_event.is_set():
                self._maybe_clear_overlay(overlay)
                try:
                    dialogue_text = self._extract_region_text(sct, self._dialogue_region)
                    dialogue_text = self._normalize_dialogue_text(dialogue_text)
                    if not dialogue_text or len("".join(dialogue_text.split())) < self._min_chars:
                        self._reset_candidate()
                        if self._wait_for_next_tick():
                            break
                        continue

                    speaker_text = ""
                    if self._name_region is not None:
                        speaker_text = self._extract_region_text(sct, self._name_region)
                        speaker_text = self._normalize_name_text(speaker_text)

                    signature = self._build_signature(speaker_text, dialogue_text)
                    if self._is_similar_signature(signature, self._last_committed_signature):
                        self._reset_candidate()
                        if self._wait_for_next_tick():
                            break
                        continue

                    if self._is_similar_signature(signature, self._candidate_signature):
                        self._candidate_hits += 1
                    else:
                        self._candidate_signature = signature
                        self._candidate_speaker = speaker_text
                        self._candidate_text = dialogue_text
                        self._candidate_hits = 1

                    if self._candidate_hits < self._stable_passes:
                        if self._candidate_hits == 1 or self._candidate_hits == self._stable_passes - 1:
                            self._emit_status(
                                f"Galgame OCR waiting for stable text... ({self._candidate_hits}/{self._stable_passes})"
                            )
                        if self._wait_for_next_tick():
                            break
                        continue

                    translated_text, cached = self._translate_candidate(
                        self._candidate_speaker,
                        self._candidate_text,
                    )
                    overlay.set_text(translated_text)
                    self._active_overlay_text = translated_text
                    self._display_deadline = time.monotonic() + self._compute_display_seconds(translated_text)
                    self._last_committed_signature = self._candidate_signature
                    self._emit_result(
                        GalgameTranslationEvent(
                            speaker=self._candidate_speaker,
                            source_text=self._candidate_text,
                            translated_text=translated_text,
                            cached=cached,
                        )
                    )
                    self._emit_status(
                        "Galgame line translated"
                        if not cached
                        else "Galgame line loaded from cache"
                    )
                    self._reset_candidate()
                except Exception as exc:
                    error_text = f"Galgame OCR error: {exc}"
                    overlay.set_text(error_text)
                    self._active_overlay_text = error_text
                    self._display_deadline = time.monotonic() + self._min_display_seconds
                    self._emit_status(error_text)

                if self._wait_for_next_tick():
                    break

    def _extract_region_text(self, sct: mss, region: ScreenRegion) -> str:
        screenshot = sct.grab(
            {
                "left": region.left,
                "top": region.top,
                "width": region.width,
                "height": region.height,
            }
        )
        image = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
        result, _ = self._ocr(image)
        if not result:
            return ""

        lines: list[str] = []
        for item in result:
            if len(item) < 2:
                continue
            text = str(item[1]).strip()
            if text:
                lines.append(text)
        return "\n".join(lines).strip()

    def _normalize_dialogue_text(self, text: str) -> str:
        normalized_lines = []
        for line in text.replace("\r", "\n").splitlines():
            compact = " ".join(line.replace("\u3000", " ").split())
            if compact:
                normalized_lines.append(compact)
        return "\n".join(normalized_lines).strip()

    def _normalize_name_text(self, text: str) -> str:
        normalized = self._normalize_dialogue_text(text)
        if not normalized:
            return ""
        return normalized.splitlines()[0][:30].strip()

    def _build_signature(self, speaker: str, dialogue: str) -> str:
        if speaker:
            return f"{speaker}||{dialogue}"
        return dialogue

    def _is_similar_signature(self, current: str, previous: str) -> bool:
        if not current or not previous:
            return False
        similarity = SequenceMatcher(a=previous, b=current).ratio()
        return similarity >= self._similarity_threshold

    def _translate_candidate(self, speaker: str, dialogue: str) -> tuple[str, bool]:
        cache_key = (speaker, dialogue)
        cached_text = self._translation_cache.get(cache_key)
        if cached_text is not None:
            return cached_text, True

        if speaker:
            translated_speaker, translated_dialogue = self._provider.translate_lines(
                [speaker, dialogue],
                target_language=self._target_language,
                context_hint=(
                    "Galgame dialogue. The first item may be a speaker name and should stay concise. "
                    "The second item is the actual dialogue line."
                ),
            )
            translated = f"{translated_speaker}\n{translated_dialogue}".strip()
        else:
            translated = self._provider.translate_lines(
                [dialogue],
                target_language=self._target_language,
                context_hint=(
                    "Galgame dialogue. Preserve tone, pauses, and dramatic delivery. Keep it readable in an overlay."
                ),
            )[0]

        self._translation_cache[cache_key] = translated
        return translated, False

    def _emit_status(self, message: str) -> None:
        if self._status_callback is not None:
            self._status_callback(message)

    def _emit_result(self, event: GalgameTranslationEvent) -> None:
        if self._result_callback is not None:
            self._result_callback(event)

    def _reset_candidate(self) -> None:
        self._candidate_signature = ""
        self._candidate_speaker = ""
        self._candidate_text = ""
        self._candidate_hits = 0

    def _wait_for_next_tick(self) -> bool:
        return self._stop_event.wait(self._interval_seconds)

    def _maybe_clear_overlay(self, overlay: OverlayWindow) -> None:
        if not self._active_overlay_text or self._display_deadline is None:
            return
        if time.monotonic() < self._display_deadline:
            return
        overlay.clear_text()
        self._active_overlay_text = ""
        self._display_deadline = None

    def _compute_display_seconds(self, text: str) -> float:
        readable_text = "".join(text.split())
        if not readable_text:
            return self._min_display_seconds
        estimated = 1.8 + (len(readable_text) / 8.0)
        return max(
            self._min_display_seconds,
            min(self._max_display_seconds, estimated),
        )
