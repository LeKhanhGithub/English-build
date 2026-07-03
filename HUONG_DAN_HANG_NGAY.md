# Huong dan tao video hang ngay

Moi ngay ban chi can nhap mot cau tieng Anh. Project se tu search clip, tai video, tao subtitle, ghep thanh video ngang, va neu can thi tao them ban doc cho TikTok/Reels/Shorts.

## 1. Mo project

Dung Git Bash:

```bash
cd ~/OneDrive/Desktop/video-builder/playphrase-video-builder
source .venv/Scripts/activate
```

Khi activate dung, dau dong lenh se co `(.venv)`.

Neu khong muon activate, thay `python` bang:

```bash
./.venv/Scripts/python.exe
```

## 2. Lenh quan trong nhat

Tao video ngang:

```bash
python main.py build "nice to meet you" --force-search
```

Tao them ban doc Reel/Shorts sau khi da build:

```bash
python main.py enhance "nice to meet you"
```

Tao nhieu video ngang trong mot lenh, toi da 5 cum:

```bash
python main.py build "nice to meet you" "how are you" "see you soon" --force-search
```

Tao nhieu Reel/Shorts trong mot lenh, sau khi cac video ngang da build xong:

```bash
python main.py enhance "nice to meet you" "how are you" "see you soon"
```

Co the paste danh sach bang dau `;`:

```bash
python main.py build "nice to meet you; how are you; see you soon" --force-search
```

Neu khong activate `.venv`, dung:

```bash
./.venv/Scripts/python.exe main.py build "nice to meet you" --force-search
./.venv/Scripts/python.exe main.py enhance "nice to meet you"
```

## 3. File ket qua nam o dau?

Video ngang de upload YouTube/Facebook:

```text
outputs/videos/nice-to-meet-you.mp4
```

Video doc cho TikTok/Reels/Shorts:

```text
outputs/reels/nice-to-meet-you-reel.mp4
```

Clip tai ve:

```text
downloads/nice-to-meet-you/clips/
```

Subtitle va metadata:

```text
downloads/nice-to-meet-you/subtitles/
downloads/nice-to-meet-you/search-results.json
downloads/nice-to-meet-you/download-report.json
```

B-roll Wikimedia cho ban Reel:

```text
downloads/nice-to-meet-you/broll/
```

## 4. Workflow de dung moi ngay

Thay cau trong dau ngoac kep:

```bash
python main.py build "CAU_TIENG_ANH" --force-search
python main.py enhance "CAU_TIENG_ANH"
```

Vi du:

```bash
python main.py build "I'm falling for you" --force-search
python main.py enhance "I'm falling for you"
```

Neu muon chon b-roll mood rieng cho ban Reel:

```bash
python main.py enhance "I'm falling for you" --broll-query "couple walking" --force-broll
```

B-roll mac dinh se xoay nhieu canh doi thuong hon va ne cac clip meeting/office.
Neu mot cum da co b-roll cu, dung `--force-broll` de tai lai clip mo dau moi.
Intro va b-roll opener se hien them nghia Trung/Nhat/Viet/Han/Tay Ban Nha/Hindi kem icon co that neu dich duoc; thoi luong
intro va opener van giu nhu cu.

Neu chi muon layout doc, khong can b-roll:

```bash
python main.py enhance "I'm falling for you" --no-broll
```

## 5. Cac lenh debug

Chi search, chua tai video:

```bash
python main.py search "nice to meet you" --force
```

Chi tai clip cua search moi nhat:

```bash
python main.py download
```

Chi ghep video ngang tu clip da tai:

```bash
python main.py merge
```

Ghep video ngang cho mot cau cu the:

```bash
python main.py merge "nice to meet you"
```

## 6. Chuong trinh dang lay video tu dau?

Thu tu nguon:

1. PlayPhrase: nguon chinh, co word timing nen subtitle co karaoke tung tu.
2. Clip.Cafe: nguon phu uu tien thu hai theo cau hinh mac dinh.
3. Comb.io: nguon phu, chi lay neu subtitle/title khop cau search.
4. Wikimedia Commons: chi dung lam b-roll hook cho lenh `enhance`.

Comb/Clip.Cafe khong co timing tung tu nhu PlayPhrase. Vi vay cac clip nay hien subtitle theo dong, va highlight mau vang doan trung voi cau search.

Co the doi thu tu nguon bang `SOURCE_PRIORITY` trong `.env`.

## 7. Cau hinh quan trong trong `.env`

```env
HEADLESS=true
MAX_PARALLEL=4
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
COMMONS_VERIFY_SSL=false

TRANSLATIONS_ENABLED=true
TRANSLATION_PROVIDER=gemini
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.5-flash
TRANSLATION_CONTACT_EMAIL=
```

Y nghia nhanh:

- `TARGET_TOTAL_CLIPS=10`: muc tieu tong so clip sau khi gom nhieu nguon.
- `SOURCE_PRIORITY=playphrase,clipcafe,comb`: thu tu xep clip vao video cuoi. Doi thanh `playphrase,comb,clipcafe` neu muon Comb truoc Clip.Cafe.
- `MAX_TOTAL_CLIPS=12`: gioi han cao nhat neu video van qua ngan.
- `MIN_TOTAL_DURATION_SECONDS=45`: neu tong clip ngan hon muc nay, chuong trinh co the tim them.
- `COMMONS_MIN_SHORT_EDGE=1080` va `COMMONS_MIN_LONG_EDGE=1920`: chi lay b-roll toi thieu 1080p de tranh bi mo.
- `COMMONS_VERIFY_SSL=false`: may nay dang can false vi Wikimedia bi loi chain SSL tren Windows. May khac co the dat true.
- `TRANSLATIONS_ENABLED=true`: hien nghia Trung/Nhat/Viet/Han/Tay Ban Nha/Hindi tren intro va b-roll opener.
- `TRANSLATION_PROVIDER=gemini`: dich tu nhien hon bang Gemini API va cache vao `downloads/<phrase-slug>/translations.json`. Neu chua co `GEMINI_API_KEY`, tool tu fallback ve phrasebook/MyMemory.
- `GEMINI_API_KEY`: API key Google AI Studio/Gemini. De trong neu tam thoi muon dung fallback.
- `GEMINI_MODEL`: mac dinh `gemini-3.5-flash`.
- `TRANSLATION_PROVIDER=phrasebook`: che do offline nhanh nhat, it tu hon.

Sau khi doi `SOURCE_PRIORITY`, hay chay `build` voi `--force-search` de tao lai search-result dung thu tu moi.

## 8. Loi hay gap

### `No module named 'pydantic'`

Ban dang chay Python global, chua activate `.venv`.

Sua bang:

```bash
source .venv/Scripts/activate
python main.py build "hello" --force-search
```

Hoac chay truc tiep:

```bash
./.venv/Scripts/python.exe main.py build "hello" --force-search
```

### PlayPhrase bi loi browser

Thu mo browser len de xem:

```bash
export HEADLESS=false
python main.py build "hello" --force-search
```

Sau khi xong, dat lai trong `.env`:

```env
HEADLESS=true
```

### `ffprobe.exe` bi Windows Application Control chan

Code da co fallback nen merge/build van co the chay. Neu van loi FFmpeg, cai lai FFmpeg bang winget va mo terminal moi:

```powershell
winget install Gyan.FFmpeg
```

## 9. Lenh nen dung nhat

```bash
python main.py build "your phrase here" --force-search
python main.py enhance "your phrase here"
```
