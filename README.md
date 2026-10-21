# Spotistats

Spotistats is a project designed to provide detailed statistics and musical insights about songs. With Spotistats, you can easily replicate the vibe of your favourite songs using music theory.

It runs as a slim panel docked to the left of the Spotify desktop app and follows whatever is playing.

## Features

- **Album Cover View**: Click the album cover to scale it to your display (Esc or Space closes it).
- **AI Chord Suggestions**: Three chord progressions that match the vibe of the current song, validated for musical consistency. Click one to save it as a MIDI file to Downloads.
- **Similar Tracks**: The three most similar songs from a ~25k-song catalog. Click one to play it (needs Spotify Premium; otherwise it opens in Spotify).
- **Responsive UI**: All Spotify, OpenAI and network calls run on worker threads.

## Upcoming Features

- **Rating System**: Rate the suggestions (the feedback box is in place but not wired yet).
- **Similar tracks for any song**: Look up songs outside the catalog from their audio features (the model supports it; the feature source isn't hooked up yet).
- **Advanced Prompting**: Customize your prompts to the LLM without having to worry about finding the necessary song statistics for your prompt.
- **Mobile App**: Access your stats on the go with a mobile app.

## Requirements

- Windows (the panel docks to Spotify's window through the Win32 API)
- Python 3.13 and the Spotify desktop app
- A Spotify developer app (client ID/secret, redirect URI `http://127.0.0.1:<port>`) and an OpenAI API key

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install
copy .env.example .env      # then fill in the keys
```

Build the similarity model once (downloads an 8 MB public dataset into `data/`, trains into `models/` in about a minute):

```bash
python -m spotistats.ml.download_dataset
python -m spotistats.ml.train
```

## Run

```bash
spotistats                  # or: python -m spotistats. The first run opens a Spotify login in the browser
spotistats --self-test      # headless check: loads the model, exits 0 if OK
```

The login token, log and chord cache live in `%LOCALAPPDATA%\Spotistats` (logs in `logs\spotistats.log`).

## Build a standalone exe

```bash
pyinstaller app.spec        # -> dist/Spotistats.exe (bundles the trained model)
dist\Spotistats.exe --self-test
```

Put the `.env` next to the exe; secrets are never bundled.

## Development

- `pytest` runs the tests in `tests/` (unit tests mirror the package layout).
- `pre-commit run --all-files` runs the linters/formatter (ruff) and file hygiene hooks.
- CI (`.github/workflows/ci.yml`) runs both on every pull request and every push to `main`.
- `python -m spotistats.ml.evaluate` compares similarity-model variants.
- Dependencies are pinned in `pyproject.toml` (`dev` extra for tooling).

## Project layout

```
src/spotistats/        the app package (python -m spotistats)
  config.py            where files live: assets, models, .env, app data
  auth.py              secrets from .env; Spotify / OpenAI clients
  assets/              icon and title font
  ui/                  main window, title bar, list boxes, fullscreen cover, theme
  workers/             QThreads: playback polling/control, data fetching
  services/            Spotify, OpenAI chord suggestions (+cache), similarity, Win32 window tracking
  music/               chord-progression schema/validation, MIDI export
  ml/                  similarity model: dataset download, dedup, features, embedding, train/evaluate
data/                  downloaded dataset (gitignored)
models/                trained model artifacts (gitignored, bundled into the exe)
tests/                 unit/ (mirrors src/spotistats/) and integration/
research/              stem-based perceptual similarity study (own venv)
run.py                 PyInstaller entry script
app.spec               PyInstaller build
```

## License

All rights reserved - see [LICENSE](LICENSE).

## Contact

For any questions or suggestions, please open an issue or contact me at [nicolas7cunderlik@gmail.com](mailto:nicolas7cunderlik@gmail.com).
