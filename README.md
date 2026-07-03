# playphrase-video-builder

Tool tao video hoc tieng Anh tu mot cau/phrase.

Ban nhap:

```bash
python main.py build "nice to meet you" --force-search
```

Project se:

1. Search PlayPhrase.
2. Lay clip free phu hop.
3. Lay them clip tu Comb.io va Clip.Cafe neu can.
4. Tai clip ve may.
5. Tao subtitle tieng Anh.
6. Ghep thanh video ngang.
7. Co the tao them ban doc Reel/Shorts voi b-roll Wikimedia Commons.

> Chi upload video khi ban co quyen su dung noi dung nguon. Tool nay khong bypass paywall, DRM, login, hay browser security. No chi dung cac media URL public ma browser/API tra ve.

## Ket qua output

Video ngang:

```text
outputs/videos/<phrase-slug>.mp4
```

Video doc Reel/Shorts:

```text
outputs/reels/<phrase-slug>-reel.mp4
```

Vi du:

```text
outputs/videos/nice-to-meet-you.mp4
outputs/reels/nice-to-meet-you-reel.mp4
```

## Cai dat

Yeu cau:

- Python 3.12+
- FFmpeg tren PATH
- Chromium cua Playwright

Tao venv va cai dependency:

```bash
cd playphrase-video-builder
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
```

Git Bash:

```bash
source .venv/Scripts/activate
pip install -r requirements.txt
python -m playwright install chromium
```

macOS/Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

FFmpeg tren Windows:

```powershell
winget install Gyan.FFmpeg
```

Dong terminal va mo lai, kiem tra:

```bash
ffmpeg -version
```

`ffprobe` duoc khuyen nghi, nhung code co fallback neu Windows Application Control chan `ffprobe.exe`.

## Cau hinh `.env`

Copy file mau:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Gia tri quan trong:

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

MAX_CLIPS=10
SOURCE_PRIORITY=playphrase,clipcafe,comb
TARGET_TOTAL_CLIPS=10
MAX_TOTAL_CLIPS=12
MIN_TOTAL_DURATION_SECONDS=45

COMB_ENABLED=true
COMB_MAX_CLIPS=5

CLIPCAFE_ENABLED=true
CLIPCAFE_MAX_CLIPS=5

COMMONS_BROLL_ENABLED=true
COMMONS_MAX_BYTES=80000000
COMMONS_MIN_SHORT_EDGE=1080
COMMONS_MIN_LONG_EDGE=1920
COMMONS_VERIFY_SSL=true

TRANSLATIONS_ENABLED=true
TRANSLATION_PROVIDER=gemini
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.5-flash
TRANSLATION_CONTACT_EMAIL=
```

Ghi chu:

- `MAX_CLIPS`: so clip PlayPhrase toi da.
- `SOURCE_PRIORITY`: thu tu uu tien khi xep clip vao video cuoi. Vi du `playphrase,clipcafe,comb` nghia la PlayPhrase truoc, Clip.Cafe thu hai, Comb.io cuoi.
- `TARGET_TOTAL_CLIPS`: muc tieu tong so clip sau khi them nguon phu.
- `MAX_TOTAL_CLIPS`: gioi han cao nhat neu tong video qua ngan.
- `MIN_TOTAL_DURATION_SECONDS`: neu tong clip ngan hon muc nay, tool co the tim them.
- `COMB_MAX_CLIPS`: toi da clip tu Comb.io.
- `CLIPCAFE_MAX_CLIPS`: toi da clip tu Clip.Cafe.
- `COMMONS_BROLL_ENABLED`: bat b-roll Wikimedia cho lenh `enhance`.
- `COMMONS_MIN_SHORT_EDGE=1080` va `COMMONS_MIN_LONG_EDGE=1920`: chi nhan b-roll toi thieu 1080p. Tang len neu ban chi muon file rat net, giam xuong neu query qua it ket qua.
- `COMMONS_VERIFY_SSL`: de `true` neu may binh thuong. Tren may nay dang de `false` vi chain SSL Wikimedia bi loi trong Windows.
- `TRANSLATIONS_ENABLED=true`: hien nghia Trung/Nhat/Viet/Han/Tay Ban Nha/Hindi tren intro va b-roll opener.
- `TRANSLATION_PROVIDER=gemini`: dung Gemini API de dich tu nhien hon nhu nguoi ban ngu, roi cache vao `downloads/<phrase-slug>/translations.json`. Neu chua co `GEMINI_API_KEY`, tool tu fallback ve phrasebook/MyMemory.
- `GEMINI_API_KEY`: API key Google AI Studio/Gemini. De trong neu tam thoi muon dung fallback.
- `GEMINI_MODEL`: mac dinh `gemini-3.5-flash`.
- `TRANSLATION_PROVIDER=phrasebook`: dung che do offline nhanh nhat, it tu hon.
- `TRANSLATION_CONTACT_EMAIL`: email tuy chon MyMemory khuyen nghi cho luu luong cao khi fallback qua MyMemory.

Neu doi `SOURCE_PRIORITY`, nen chay lai:

```bash
python main.py build "your phrase" --force-search
```

## Lenh su dung

Search:

```bash
python main.py search "nice to meet you" --force
```

Download:

```bash
python main.py download
```

Merge video ngang:

```bash
python main.py merge
```

Build tu dau den cuoi:

```bash
python main.py build "nice to meet you" --force-search
```

Tao ban Reel/Shorts:

```bash
python main.py enhance "nice to meet you"
```

Xu ly nhieu cum trong mot lenh, toi da 5 cum, tool se chay lan luot theo dung thu tu:

```bash
python main.py build "nice to meet you" "how are you" "see you soon" --force-search
python main.py enhance "nice to meet you" "how are you" "see you soon"
```

Neu muon paste thanh mot danh sach trong cung mot cap ngoac kep, ngan cach bang dau `;`:

```bash
python main.py build "nice to meet you; how are you; see you soon" --force-search
```

Chon b-roll query rieng:

```bash
python main.py enhance "I'm falling for you" --broll-query "couple walking" --force-broll
```

Mac dinh b-roll se xoay nhieu query doi thuong nhu walking, street, park, station,
cafe... va tranh cac clip meeting/office neu ban khong yeu cau ro. Neu mot cum da
co b-roll cache cu, them `--force-broll` de doi clip mo dau moi.
Intro va b-roll opener se hien them nghia Trung/Nhat/Viet/Han/Tay Ban Nha/Hindi kem icon co that neu dich duoc; thoi luong
intro va opener khong doi.

Khong dung b-roll:

```bash
python main.py enhance "nice to meet you" --no-broll
```

Chi dinh output rieng:

```bash
python main.py build "hello" --output outputs/videos/my-video.mp4
python main.py enhance "hello" --output outputs/reels/my-reel.mp4
```

Luu y: `--output` va `--input` chi dung cho mot cum. Khi nhap nhieu cum, tool tu dat
file theo slug rieng cua tung cum trong `outputs/videos/` hoac `outputs/reels/`.

## Folder du lieu

```text
downloads/
  latest-search.json
  search-cache/
  <phrase-slug>/
    search-results.json
    download-report.json
    clips/
      001.mp4
      002.mp4
    subtitles/
      001.ass
      001.txt
      001.json
    broll/
      commons-broll.json

outputs/
  videos/
    <phrase-slug>.mp4
  reels/
    <phrase-slug>-reel.mp4

logs/
  run-YYYYMMDD-HHMMSS.log
```

## Cac nguon video

### PlayPhrase

Nguon chinh. Clip PlayPhrase co word timing nen subtitle co karaoke tung tu khi API cung cap timing.

### Clip.Cafe

Nguon phu uu tien thu hai theo cau hinh mac dinh. Dung de bu clip khi PlayPhrase chua du so luong hoac video qua ngan. Neu co VTT caption, tool dung caption do de burn subtitle va highlight phrase.

### Comb.io

Nguon phu. Tool chi lay clip neu subtitle/title khop phrase da search. Cac ket qua long leo nhu `fall for that` se bi bo qua khi search `I'm falling for you`.

### Wikimedia Commons

Dung cho b-roll hook cua `enhance`. Tool chi lay b-roll dat nguong chat luong theo `COMMONS_MIN_SHORT_EDGE` va `COMMONS_MIN_LONG_EDGE`. Video b-roll goc duoc dat net o giua khung doc; nen blur chi la nen phu de lap day 9:16, khong phai video chinh.

Metadata va credit nam trong:

```text
downloads/<phrase-slug>/broll/commons-broll.json
```

### Nguon thu 4 dang nghien cuu

Da test Frinkiac/Morbotron: API search subtitle hoat dong, nhung endpoint GIF/MP4 public khong on dinh va nguon bi gioi han vao mot vai show. GetYarn hien van bi Cloudflare 403. Vi vay code chua bat nguon thu 4 mac dinh de tranh chen clip kem on dinh vao video.

## Subtitle

- PlayPhrase: karaoke tung tu neu co word timing.
- Comb.io/Clip.Cafe: subtitle theo dong, highlight mau vang doan trung voi phrase.
- Subtitle dai se duoc wrap xuong dong de tranh tran video.

## Cach dung hang ngay

```bash
python main.py build "your phrase here" --force-search
python main.py enhance "your phrase here"
```

Xem ket qua:

```text
outputs/videos/
outputs/reels/
```

## FAQ

### Loi `No module named 'pydantic'`

Ban chua activate `.venv`.

Sua:

```bash
source .venv/Scripts/activate
python main.py build "hello" --force-search
```

Hoac:

```bash
./.venv/Scripts/python.exe main.py build "hello" --force-search
```

### Muon mo browser PlayPhrase de debug?

Trong Git Bash:

```bash
export HEADLESS=false
python main.py build "hello" --force-search
```

Hoac sua `.env`:

```env
HEADLESS=false
```

### `ffprobe.exe` bi Windows chan?

Code da co fallback metadata. Neu FFmpeg cung bi chan, cai lai FFmpeg bang winget:

```powershell
winget install Gyan.FFmpeg
```

### Co the upload video khong?

Chi upload khi ban co quyen su dung clip nguon va b-roll. Kiem tra license trong metadata, dac biet voi Wikimedia Commons.

## Test

```bash
python -m pytest
```
