# AI Handoff

This file is for the next AI agent working in this repo. It is not end-user documentation.

## Project identity

- Repo root: `H:\AI字幕`
- Product type: Windows-focused Python desktop GUI for subtitle and OCR translation
- Main user-facing entry: `launch_gui.pyw`
- Main GUI module: `src/ai_subtitle/gui.py`
- Packaging target: PyInstaller Windows exe via `build_exe.bat`

## What the app currently does

1. Video or audio to `.srt`
   - Local transcription with `faster-whisper`
   - Optional automatic translation of the generated `.srt`

2. Existing `.srt` translation
   - Uses OpenAI-compatible chat completion API

3. Generic live game OCR
   - OCR a fixed screen region
   - Translate the text in real time
   - Show translation in overlay window

4. Galgame-specific OCR mode
   - Separate dialogue box region
   - Optional separate speaker name region
   - Wait-for-stable-text logic for letter-by-letter text reveal
   - Translation cache
   - In-app history panel

## Current implementation status

### Last committed release

- Last local commit already created and pushed previously:
  - `1dda411 Release v0.2.0 with noisy-scene transcription and GUI polish`

### Important current working tree state

The working tree is currently dirty. At the time this file was created, these files had uncommitted local changes:

- `README.md`
- `src/ai_subtitle/game_ocr.py`
- `src/ai_subtitle/gui.py`

These uncommitted changes are the new galgame OCR feature and related README updates. Be careful not to lose them.

## User preferences and collaboration constraints

- The user prefers direct action over discussion.
- The user does not want repeated permission-style questions for normal code edits.
- The user likes GUI-first workflows, visible progress, logs, and polished visuals.
- The user cares about privacy:
  - real API keys must stay out of git
  - `.env` must remain ignored
- The user is comfortable with exe/bat distribution on Windows.
- The user often asks for practical UX changes rather than architecture discussion.

## Key modules

### GUI

- `src/ai_subtitle/gui.py`
  - Main window class: `SubtitleTranslatorGUI`
  - Builds notebook tabs for:
    - `Video Subtitle`
    - `Galgame`
    - `Game OCR`
  - Also contains the progress window and the pixel animation

Relevant entry points in `gui.py`:

- `SubtitleTranslatorGUI` at around line 435
- `_build_galgame_tab()` at around line 817
- `_start_galgame_ocr()` at around line 1217

### OCR translators

- `src/ai_subtitle/game_ocr.py`

Contains:

- `GameOCRTranslator`
  - Generic OCR loop for any fixed subtitle region
- `GalgameOCRTranslator`
  - Galgame-specific OCR loop
  - Waits for stable text before translating
  - Supports optional speaker name region
  - Emits structured history events back to GUI

Relevant classes in `game_ocr.py`:

- `GameOCRTranslator` at around line 33
- `GalgameOCRTranslator` at around line 190

### Overlay

- `src/ai_subtitle/overlay.py`
  - Small always-on-top translation overlay
  - Polls a queue from worker threads

### Video transcription

- `src/ai_subtitle/transcribe.py`
  - `transcribe_media_to_srt()` at around line 35
  - `resolve_transcription_settings()` at around line 180

Important behavior:

- Uses local `faster-whisper`
- Supports profiles:
  - `balanced`
  - `high_quality`
  - `noisy_scene`
- `noisy_scene` can preprocess audio with `PyAV` and cleanup steps before Whisper
- If preprocessing fails, transcription now falls back to the original audio instead of failing the whole task

### Translation provider

- `src/ai_subtitle/providers/openai_compatible.py`
  - Uses `POST {base_url}/chat/completions`
  - Expects an OpenAI-compatible API shape
  - Sends a JSON-only translation prompt

## Galgame OCR behavior

The new galgame mode is intentionally different from generic game OCR.

Current galgame flow:

1. OCR the dialogue region
2. Optionally OCR the name region
3. Normalize text
4. Ignore empty or too-short dialogue
5. Require the same text to stay visible for `stable_passes`
6. Compare against last committed line using similarity threshold
7. Translate only once per stable line
8. Cache translations by `(speaker, dialogue)`
9. Show translated result in overlay
10. Append result into GUI history panel

This is a practical OCR-first galgame pipeline, not a text hook solution.

## What was added recently

### Earlier completed work

- GUI progress window with:
  - progress bar
  - log view
  - pixel-art rider animation
- Scrollable main GUI
- Video tab:
  - play selected media
  - open containing folder
- Subtitle auto-clear timing improvements for game overlay
- Better horse/rider animation art
- Day/night background cycle with sun/moon/stars and roaming background entities
- Public repo files:
  - `LICENSE`
  - `CONTRIBUTING.md`
  - `SECURITY.md`
  - `CHANGELOG.md`

### Very recent but not yet committed

- New `Galgame` tab in GUI
- New `GalgameOCRTranslator`
- History panel for galgame lines
- Optional speaker name OCR region
- Stable text wait logic for letter-by-letter dialogue
- README note about galgame mode

## Dependencies and packaging notes

Declared in `pyproject.toml`:

- `faster-whisper`
- `rapidocr-onnxruntime`
- `httpx`
- `mss`
- `Pillow`
- `python-dotenv`
- `av`
- `numpy`

PyInstaller spec:

- `AI_Subtitle_Translator.spec`
- Includes hidden imports and dynamic libs for `av` and `ctranslate2`

Packaging gotcha:

- If the exe misses noisy-scene preprocessing support, inspect the spec file first.

## Privacy and config handling

- Real credentials are expected in `.env`
- `.env` is intentionally gitignored
- User explicitly asked that secrets must never be uploaded
- The app supports automatic config loading and local overrides from GUI

Important files:

- `.env`
- `.env.example`
- `.gitignore`
- `src/ai_subtitle/config.py`

## Git and remote state

- Current remote was changed to:
  - `https://github.com/Amugulen/AISubitleTranslator.git`
- A push to that remote succeeded earlier in this session for commit `1dda411`

## Known rough edges / likely next steps

1. Galgame region selection is still manual.
   - User currently has to type `left,top,width,height`
   - A screen region picker would be a strong next improvement

2. Galgame OCR preprocessing is still basic.
   - No dedicated image preprocessing for white text with dark outline
   - No special handling for ruby/furigana text

3. No text hook mode yet.
   - Current galgame solution is OCR-based only
   - Hooking external text sources is a natural future direction

4. No offline galgame extraction pipeline yet.
   - No script unpacking
   - No local translation memory export/import

5. Overlay and history are functional, but not yet galgame-specialized in presentation.
   - Could add better speaker formatting
   - Could add copy/export history
   - Could add dual-column original/translation history view

## Run and validate quickly

Recommended quick validation flow:

1. Use the project venv:
   - `H:\AI字幕\.venv\Scripts\python.exe`

2. Launch GUI:
   - `python launch_gui.pyw`
   - or double-click `launch_gui.bat`

3. Import sanity checks:
   - `src/ai_subtitle/gui.py`
   - `src/ai_subtitle/game_ocr.py`
   - `src/ai_subtitle/transcribe.py`

Recent local checks that already passed during this session:

- AST parse of `gui.py`
- AST parse of `game_ocr.py`
- Import of `ai_subtitle.gui`
- Import of `ai_subtitle.game_ocr`
- Import of `ai_subtitle.transcribe`

## Safe editing guidance

- Do not overwrite `.env`
- Do not commit secrets
- Do not revert unrelated user changes
- The repo may already contain useful uncommitted work; inspect `git status` first
- Prefer preserving current GUI behavior and extending it, because the user cares about UX continuity

## If you need a first good task

Best next task candidates:

1. Add a screen region picker for galgame dialogue and speaker name boxes
2. Add galgame-specific OCR image preprocessing
3. Improve galgame history view and export
4. Add external text hook ingestion mode without replacing the existing OCR mode
