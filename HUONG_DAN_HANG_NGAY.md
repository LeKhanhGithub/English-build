# Huong dan tao video hang ngay

File nay la quy trinh ngan gon de moi ngay ban chi can nhap mot cau tieng Anh va tao video MP4.

## 1. Loi `No module named 'pydantic'` la gi?

Loi nay xay ra khi ban chay:

```bash
python main.py search "nice to meet you"
```

nhung lenh `python` dang tro toi Python global cua may, khong phai Python trong moi truong ao `.venv`.

Dependencies nhu `pydantic`, `playwright`, `rich`, `typer` da duoc cai trong:

```text
.venv/
```

Vi vay ban can chay bang Python trong `.venv`, hoac kich hoat `.venv` truoc.

## 2. Cach chay dung trong Git Bash

Ban dang dung Git Bash / MINGW64, hay chay:

```bash
cd ~/OneDrive/Desktop/video-builder/playphrase-video-builder
source .venv/Scripts/activate
python main.py build "nice to meet you" --force-search
```

Sau khi activate thanh cong, dau dong lenh thuong se hien them `(.venv)`.

Tu luc do, ban co the dung:

```bash
python main.py build "hello" --force-search
python main.py build "how are you" --force-search
python main.py build "nice to meet you" --force-search
```

## 3. Cach chay khong can activate

Neu khong muon activate `.venv`, hay go truc tiep:

```bash
cd ~/OneDrive/Desktop/video-builder/playphrase-video-builder
./.venv/Scripts/python.exe main.py build "nice to meet you" --force-search
```

Day la cach it nham nhat trong Git Bash.

## 4. Lenh dung moi ngay

Moi ngay ban chi can thay phan trong dau ngoac kep:

```bash
./.venv/Scripts/python.exe main.py build "CAU_TIENG_ANH_CAN_TIM" --force-search
```

Vi du:

```bash
./.venv/Scripts/python.exe main.py build "nice to meet you" --force-search
```

Ket qua se nam trong:

```text
outputs/nice-to-meet-you.mp4
```

Mac dinh hien tai:

- Lay nhieu clip free nhat ma PlayPhrase tra ve, toi da 10 clip PlayPhrase.
- Neu `COMB_ENABLED=true`, lay them clip public tu `comb.io` sau PlayPhrase.
- Mac dinh `COMB_MAX_CLIPS=5`, nen thuong se co 5 PlayPhrase + 5 Comb neu ca hai nguon co ket qua.
- Khong them outro / man ket thuc.
- Moi clip co subtitle rieng trong `downloads/<phrase>/subtitles/`.
- Video final se burn subtitle karaoke tieng Anh theo tung tu neu PlayPhrase co timing.
- Clip Comb co subtitle tieng Anh theo tung dong loi thoai that trong timeline.
- Comb khong expose timing tung tu nhu PlayPhrase, nen Comb khong dung karaoke gia.
- Trong clip Comb, text trung voi phrase da search se duoc highlight mau vang; text khac mau trang binh thuong.
- Subtitle dai se duoc xuong dong de tranh tran video.

## 5. Vi sao nen dung `--force-search`?

`--force-search` bat chuong trinh tim lai PlayPhrase tu dau, khong lay search cache cu.

Nen dung tuy chon nay cho workflow hang ngay de dam bao:

- Video dung voi cau vua search.
- Khong dung lai JSON cache cu.
- Khong bi nham neu PlayPhrase doi ket qua theo thoi gian.

Code hien tai cung da duoc sua de:

- Khong bat clip mac dinh cua PlayPhrase truoc khi search.
- Chi merge cac clip thuoc search-result hien tai.
- Chi skip clip da tai neu URL nguon khop voi report cu.
- Lay clip tu API search cua PlayPhrase truoc, nen co du title, movie, video URL va word timing.
- Gioi han toi da 10 clip free moi phrase.
- Them source phu `comb.io` sau PlayPhrase vi GetYarn hien bi Cloudflare Turnstile.
- Khong them outro mac dinh.

## 6. Cac lenh rieng le khi can debug

Chi search, chua tai video:

```bash
./.venv/Scripts/python.exe main.py search "nice to meet you" --force
```

Chi download clip cua search moi nhat:

```bash
./.venv/Scripts/python.exe main.py download
```

Chi merge clip cua search moi nhat:

```bash
./.venv/Scripts/python.exe main.py merge
```

Full pipeline:

```bash
./.venv/Scripts/python.exe main.py build "nice to meet you" --force-search
```

## 7. Tuy chinh source phu Comb

Trong file `.env`:

```env
COMB_ENABLED=true
COMB_MAX_CLIPS=5
COMB_URL=https://comb.io
```

Neu chi muon dung PlayPhrase:

```env
COMB_ENABLED=false
```

Neu muon lay nhieu clip Comb hon, tang toi da 10:

```env
COMB_MAX_CLIPS=10
```

## 8. Noi xem file ket qua

Video MP4 cuoi cung:

```text
outputs/<ten-cau-da-slug>.mp4
```

Vi du:

```text
outputs/nice-to-meet-you.mp4
outputs/hello.mp4
outputs/how-are-you.mp4
```

Clip tai ve:

```text
downloads/<ten-cau-da-slug>/clips/
```

Subtitle tieng Anh di kem:

```text
downloads/<ten-cau-da-slug>/subtitles/
```

Trong folder subtitle se co:

```text
001.ass   # subtitle karaoke de burn vao video
001.txt   # cau tieng Anh dang plain text
001.json  # word timing goc tu PlayPhrase
```

Search JSON:

```text
downloads/<ten-cau-da-slug>/search-results.json
```

Log moi lan chay:

```text
logs/
```

## 9. Neu PlayPhrase bi loi browser

Thu chay voi browser hien len:

```bash
HEADLESS=false ./.venv/Scripts/python.exe main.py build "nice to meet you" --force-search
```

Neu dung Git Bash tren Windows ma bien moi truong tren khong an, dung:

```bash
export HEADLESS=false
./.venv/Scripts/python.exe main.py build "nice to meet you" --force-search
```

Sau do muon quay ve headless:

```bash
export HEADLESS=true
```

## 10. Neu muon lam sach cache cu

Thuong thi khong can, vi `--force-search` va download report da xu ly.

Neu van muon xoa cache cua mot phrase cu, co the xoa folder tuong ung trong:

```text
downloads/
```

Vi du xoa cache cua `hello`:

```bash
rm -rf downloads/hello
rm -f downloads/search-cache/hello.json
```

Chi xoa dung folder phrase ban muon lam moi.
