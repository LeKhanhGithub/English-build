# playphrase-video-builder

Create English learning videos from one English phrase.

The app searches PlayPhrase first, then optionally appends public clips from comb.io, downloads exposed MP4 media, saves English subtitle sidecars, burns subtitles into each clip, adds an optional intro title card, and exports one final MP4.

> Use this only for content you have the right to download, edit, and upload. PlayPhrase clips may contain copyrighted material. This tool does not bypass paywalls, DRM, authentication, or browser security controls; it only uses media URLs exposed to the browser.

## Features

- Playwright browser automation for PlayPhrase search.
- Search result JSON cache.
- Parallel downloads with retries, progress bars, resume support, and skip-existing behavior.
- HLS playlist download support through FFmpeg.
- FFmpeg merge pipeline.
- Fast concat without re-encoding when possible.
- Automatic normalization when codecs, dimensions, or audio streams differ.
- PlayPhrase English karaoke subtitle overlay on every clip when word timings are available.
- Comb.io line-level subtitles are extracted from the selected timeline; searched text is highlighted, and long subtitle lines are wrapped.
- Optional comb.io fallback source appended after PlayPhrase clips.
- Optional 2-second intro and optional outro.
- Per-run log files in `logs/`.
- Works on Windows, macOS, and Linux.

## Project Structure

```text
playphrase-video-builder/
  README.md
  pyproject.toml
  requirements.txt
  .env.example
  main.py
  src/
    __init__.py
    main.py
    config.py
    browser.py
    search.py
    downloader.py
    merger.py
    subtitle.py
    utils.py
  assets/
  downloads/
  outputs/
  logs/
  tests/
```

## Requirements

- Python 3.12+
- FFmpeg and FFprobe on `PATH`
- Chromium browser installed by Playwright

## Installation With uv

```bash
cd playphrase-video-builder
uv venv
```

Windows:

```powershell
.venv\Scripts\activate
uv pip install -r requirements.txt
python -m playwright install chromium
```

macOS/Linux:

```bash
source .venv/bin/activate
uv pip install -r requirements.txt
python -m playwright install chromium
```

## Installation With pip

```bash
cd playphrase-video-builder
python -m venv .venv
```

Windows:

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
```

macOS/Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Installation With Poetry

```bash
cd playphrase-video-builder
poetry install
poetry run python -m playwright install chromium
```

## FFmpeg Installation

### Windows

Using winget:

```powershell
winget install Gyan.FFmpeg
```

Close and reopen the terminal, then verify:

```powershell
ffmpeg -version
ffprobe -version
```

### macOS

```bash
brew install ffmpeg
ffmpeg -version
ffprobe -version
```

### Linux

Ubuntu/Debian:

```bash
sudo apt update
sudo apt install ffmpeg
ffmpeg -version
ffprobe -version
```

Fedora:

```bash
sudo dnf install ffmpeg
```

## Setup

Copy the example environment file:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Default `.env` values:

```env
HEADLESS=true
DOWNLOAD_FOLDER=downloads
OUTPUT_FOLDER=outputs
LOGS_FOLDER=logs
ASSETS_FOLDER=assets
TEMP_FOLDER=.tmp
PLAYWRIGHT_TIMEOUT=45000
MAX_PARALLEL=4
RETRIES=3
RETRY_BACKOFF=1.5
SEARCH_MAX_ROUNDS=30
MAX_CLIPS=10
COMB_ENABLED=true
COMB_MAX_CLIPS=5
COMB_URL=https://comb.io
PLAYPHRASE_URL=https://www.playphrase.me
```

Useful settings:

- `HEADLESS=false` opens a visible browser, which is useful when PlayPhrase changes its UI or asks for manual interaction.
- `MAX_PARALLEL=4` controls simultaneous downloads.
- `MAX_CLIPS=10` downloads up to 10 free clips. The project enforces a hard cap of 10 even if this is set higher.
- `COMB_ENABLED=true` appends comb.io clips after PlayPhrase clips.
- `COMB_MAX_CLIPS=5` adds up to five comb.io clips. Set up to `10` if you want more.
- `SEARCH_MAX_ROUNDS=30` controls scrolling and next/load-more collection rounds.

## Usage

Search a phrase and save JSON:

```bash
python main.py search "nice to meet you"
```

Download clips from the latest search:

```bash
python main.py download
```

Merge the latest downloaded clips:

```bash
python main.py merge
```

Build everything automatically:

```bash
python main.py build "nice to meet you"
```

The final video is saved as:

```text
outputs/nice-to-meet-you.mp4
```

You can also use the installed command:

```bash
playphrase-video-builder build "how are you"
```

## Common Options

Force a fresh PlayPhrase search instead of using cached JSON:

```bash
python main.py search "hello" --force
python main.py build "hello" --force-search
```

Disable intro, or explicitly enable outro:

```bash
python main.py build "how are you" --no-intro
python main.py build "how are you" --outro
```

Disable subtitle overlay:

```bash
python main.py build "how are you" --no-subtitles
```

Choose a custom output path:

```bash
python main.py build "nice to meet you" --output outputs/custom.mp4
```

Open a visible browser:

```bash
HEADLESS=false python main.py build "hello"
```

Windows PowerShell:

```powershell
$env:HEADLESS="false"
python main.py build "hello"
```

## Output Files

For phrase `nice to meet you`:

```text
downloads/
  latest-search.json
  search-cache/
    nice-to-meet-you.json
  nice-to-meet-you/
    search-results.json
    download-report.json
    clips/
      001.mp4
      002.mp4
      003.mp4

outputs/
  nice-to-meet-you.mp4

logs/
  run-YYYYMMDD-HHMMSS.log
```

## Screenshots

Search command:

```text
[screenshot placeholder: rich search results table]
```

Download command:

```text
[screenshot placeholder: parallel download progress bars]
```

Final video:

```text
[screenshot placeholder: phrase subtitle over video clip]
```

## How It Works

1. Playwright opens PlayPhrase in Chromium.
2. The scraper submits the phrase using visible search controls or URL fallbacks.
3. It collects media from video tags, source tags, download links, data attributes, and network responses.
4. Results are saved as JSON and cached by phrase.
5. The downloader saves clips as `001.mp4`, `002.mp4`, `003.mp4`, and so on.
6. Subtitle sidecars are saved as `.ass`, `.txt`, and `.json` for every clip.
7. FFmpeg first tries to merge without re-encoding when subtitles, intro, and outro are disabled.
8. When rendering is required, FFmpeg normalizes all clips to a shared MP4 profile and burns PlayPhrase karaoke subtitles into each clip.
8. Temporary render files are removed automatically.

## Testing

```bash
pytest
```

Optional linting:

```bash
ruff check .
```

## Troubleshooting

### Playwright says the browser is missing

Run:

```bash
python -m playwright install chromium
```

### FFmpeg missing

Install FFmpeg and verify both commands work:

```bash
ffmpeg -version
ffprobe -version
```

### No clips found

Try:

```bash
HEADLESS=false python main.py search "your phrase" --force
```

If the visible browser shows no PlayPhrase results, use a different phrase. If results appear but the app finds none, PlayPhrase likely changed its page structure. Keep `HEADLESS=false`, rerun with `--verbose`, and inspect the latest log in `logs/`.

### Download fails halfway

Rerun the same command. Partial `.part` files are resumed when the server supports HTTP range requests. Existing complete files are skipped.

### Merge fails because codecs differ

Run the default merge command. The default path normalizes clips automatically:

```bash
python main.py merge
```

Fast stream-copy concat is only used when you disable intro, outro, and subtitles:

```bash
python main.py merge --no-intro --no-outro --no-subtitles
```

### Text is too large or too small

Subtitle and title-card font sizes are adaptive based on output resolution. The output resolution follows the first downloaded clip.

## FAQ

### Can I type only one phrase per day?

Yes. The normal workflow is:

```bash
python main.py build "nice to meet you"
```

### Where is the search JSON?

The latest result is stored at:

```text
downloads/latest-search.json
```

Each phrase also gets:

```text
downloads/search-cache/<phrase-slug>.json
downloads/<phrase-slug>/search-results.json
```

### Does it download the highest quality?

The scraper ranks discovered media sources and prefers HLS playlists first, then MP4/M4V sources with higher resolution or bitrate hints in the URL. If PlayPhrase exposes only one source, that source is used.

### Does it bypass DRM or private downloads?

No. It only uses media URLs visible to the browser during normal page loading.

### Can I run it on Windows?

Yes. Use PowerShell, install FFmpeg, install Python 3.12, install dependencies, then run:

```powershell
python main.py build "hello"
```

### Can I upload the final MP4?

Only upload videos when you have the required rights or permission for the source clips and your use case.
