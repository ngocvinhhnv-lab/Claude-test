# TikTok Video Studio

Ứng dụng web dựng video bán hàng TikTok: **tự quay source → lấy kịch bản từ video đối thủ → lồng giọng tiếng Việt → đầy đủ chữ và phụ đề → xuất video 9:16**.

## Chạy ứng dụng web

Cần **Python 3.10+** và **ffmpeg** (bản đầy đủ, có `libass` và `zscale`).

| Hệ điều hành | Cài ffmpeg | Chạy app |
|---|---|---|
| Windows | Tải bản "full" tại gyan.dev/ffmpeg, thêm thư mục `bin` vào PATH | Bấm đúp `chay_app.bat` |
| macOS | `brew install ffmpeg` | `./chay_app.sh` |
| Linux | `sudo apt install ffmpeg` | `./chay_app.sh` |

Hướng dẫn từng bước cho nhân viên (Windows): [`HUONG_DAN_WINDOWS.pdf`](HUONG_DAN_WINDOWS.pdf) (nguồn HTML ở `docs/huong_dan_windows/`).

App mở tại http://127.0.0.1:8000. Để máy khác trong mạng nội bộ dùng chung: `./chay_app.sh --host 0.0.0.0`. Dữ liệu (video, kịch bản, video xuất ra) lưu trong thư mục `data/`.

### Quy trình

1. **Kịch bản.** Upload video đối thủ (tải từ TikTok về) hoặc dán link TikTok/Facebook (app tự tải bằng yt-dlp, được cập nhật mỗi lần mở app). AI xem khung hình, đọc chữ, nghe lời thoại, rồi tách thành từng cảnh: cảnh quay gì, lời đọc, chữ trên màn hình, độ dài. Sau đó bấm **Viết lại cho sản phẩm của tôi**: AI giữ cấu trúc và nhịp nhưng viết lời mới, không bịa giá hay khuyến mãi. Thư viện có sẵn 3 kịch bản mẫu KB1–KB3 và 40 kịch bản của kế hoạch tuần 05–11/10/2026 (`kich_ban/tuan_2026_10_05.json`), có ô tìm kiếm theo mã, sản phẩm, kênh. Kịch bản còn ô `[kiểm tra]` trong lời đọc sẽ bị chặn xuất video cho tới khi điền thông tin thật.
2. **Video nguồn.** Upload video tự quay, được nhiều file một lúc. App tạo bản xem thử, chia thành các đoạn ngắn và tự chuyển màu video HDR của iPhone.
3. **Dựng video.** Từ kịch bản bấm **Dựng video từ kịch bản này**, rồi:
   - **Chọn cảnh:** bấm **AI ghép cảnh tự động** (AI chọn đoạn nguồn cho từng cảnh và báo cảnh còn thiếu), hoặc tự chọn từng đoạn.
   - **Giọng đọc và nhạc:** chọn giọng, nhạc nền, khung hình.
   - **Xuất:** bấm **Xuất video**.

### Video xuất ra

- **Giọng đọc quyết định nhịp dựng.** Mỗi cảnh dài đúng bằng lời đọc. Nếu đoạn quay ngắn hơn lời, app tự lấy dài thêm trong video nguồn, quay chậm, hoặc giữ khung cuối.
- **Chữ đầy đủ:** chữ trên màn hình theo từng cảnh, phụ đề chạy theo lời đọc (chữ trắng viền đen). Tất cả nằm trong vùng an toàn, không bị thanh tab, cột nút và caption của TikTok che.
- **Âm thanh:** nhạc nền tự nhỏ lại khi có giọng đọc. Có thể giảm tiếng gốc của video.
- **Đăng bài:** caption và hashtag sẵn để sao chép.

### Cài đặt trong app

- **Anthropic API key** (console.anthropic.com): cần cho bóc kịch bản, viết lại và ghép cảnh tự động. Dùng model `claude-opus-5`, có bật fallback khi bị từ chối.
- **Giọng đọc tiếng Việt:**
  - **Microsoft Edge:** miễn phí, không cần key. Giọng Hoài My (nữ), Nam Minh (nam).
  - **Azure AI Speech:** cùng giọng, qua API chính thức, cần key.
  - **FPT.AI:** 8 giọng Bắc/Trung/Nam, cần key.
  - **Offline:** giọng máy, chỉ để thử khi không có mạng. Cần cài `espeak-ng`.
- **Logo:** chèn góc trên phải video.
- **Tuỳ chọn thêm:**
  - `pip install faster-whisper` để chuyển lời thoại video đối thủ thành chữ, giúp AI bóc kịch bản chính xác hơn.

---

# Công cụ dòng lệnh: tạo nhiều video từ 1 video gốc

`make_videos.py` cắt một video gốc thành nhiều video ngắn. Công cụ đổi khung hình cho từng nền tảng (TikTok, Reels, Shopee Video, YouTube) và có thể chèn chữ, logo, nhạc nền.

## Cài đặt

Cần Python 3.8+ và ffmpeg. Nếu máy chưa có ffmpeg:

```bash
pip install imageio-ffmpeg
```

## Cách 1 — Tự động chia

```bash
# Cắt mỗi 15 giây, xuất khung 9:16
python make_videos.py goc.mp4 --every 15

# Cắt theo chuyển cảnh, mỗi video dài 8–30 giây, xuất cả 9:16 và 1:1
python make_videos.py goc.mp4 --scenes --min 8 --max 30 --ratio 9:16,1:1

# Thêm chữ, logo, nhạc nền, fade
python make_videos.py goc.mp4 --scenes --text "Giảm 20% hôm nay" \
    --logo logo.png --music nhac.mp3 --fade 0.5
```

Thêm `--dry-run` để xem trước sẽ cắt những đoạn nào mà chưa xuất video.
Thêm `--print-config > config.json` để lấy file cấu hình, chỉnh tay rồi chạy theo cách 2.

## Cách 2 — Theo file cấu hình

```bash
python make_videos.py config.json
```

Xem file mẫu tại [`vi_du/config_mau.json`](vi_du/config_mau.json). Đường dẫn trong file được tính từ thư mục chứa file cấu hình.

```json
{
  "source": "goc.mp4",
  "output_dir": "output",
  "defaults": { "ratio": "9:16", "logo": "logo.png" },
  "videos": [
    { "name": "hook_1", "clips": [["0:00", "0:08"]], "text": "Pha chuẩn quán 5 phút!" },
    { "name": "highlight", "clips": [["0:02", "0:06"], ["0:14", "0:18"]], "speed": 1.25 },
    { "name": "da_nen_tang", "clips": ["0:12-0:22"], "ratio": ["9:16", "1:1", "16:9"] }
  ]
}
```

### Dựng theo kịch bản (từng cảnh)

Thay cho `clips`, dùng `beats`. Mỗi cảnh gồm một đoạn cắt và chữ riêng, thời gian hiện chữ được tính tự động theo độ dài cảnh:

```json
"beats": [
  { "canh": "Hook", "clip": ["0:03", "0:06"], "text": "Những điều bố mẹ chưa từng nói với con",
    "sub": "Có những điều bố mẹ ngại nói..." },
  { "canh": "CTA", "clip": ["1:10", "1:14"], "text": "Chỉ 48k\nBấm giỏ ngay", "pos": "center" }
]
```

`text` là chữ trên màn hình (`pos`: `top` / `center` / `bottom`, mặc định `top`), `sub` là lời thoại hiện ở dưới, `canh` chỉ để ghi chú. Kịch bản KB1–KB3 dựng sẵn nằm ở [`kich_ban/kb1_kb3.json`](kich_ban/kb1_kb3.json).

`defaults` áp dụng cho mọi video. Tuỳ chọn đặt trong từng video sẽ ghi đè lên `defaults`.

| Tuỳ chọn | Ý nghĩa | Mặc định |
|---|---|---|
| `clips` | Các đoạn cần lấy, nhiều đoạn thì ghép nối. Dạng `["0:05","0:20"]`, `"0:05-0:20"`, `"end"` = hết video | cả video |
| `ratio` | `9:16`, `1:1`, `4:5`, `16:9`, `original`, hoặc danh sách để xuất nhiều khung | `9:16` |
| `fit` | `blur` (nền mờ), `crop` (cắt tràn khung), `pad` (viền đen) | `blur` |
| `speed` | Tốc độ, ví dụ `1.25` hoặc `0.5` | `1.0` |
| `text` / `text_pos` | Chữ hiện suốt video, vị trí `top` / `center` / `bottom` | — / `top` |
| `captions` | Chữ theo thời gian: `[{"start":0,"end":3,"text":"...","pos":"bottom"}]`, tính theo giây của video xuất ra | — |
| `logo` / `logo_pos` / `logo_size` | Ảnh logo (PNG nền trong), góc đặt, kích thước so với cạnh ngắn | — / `top-right` / `0.18` |
| `music` / `music_volume` | Nhạc nền (tự lặp nếu ngắn hơn video), âm lượng | — / `0.3` |
| `keep_audio` / `audio_volume` | Giữ tiếng gốc khi có nhạc nền, âm lượng tiếng gốc | `true` / `1.0` |
| `voice` / `voice_volume` | File giọng đọc (thu âm hoặc TTS), phát từ giây 0 của video | — / `1.0` |
| `fade` | Số giây fade in/out cho hình và tiếng | `0` |
| `fps`, `crf`, `font` | Số khung hình/giây, chất lượng (càng nhỏ càng nét), phông chữ | `30`, `20`, `DejaVu Sans` |

Video xuất ra ở dạng MP4 (H.264 + AAC), dùng được cho TikTok, Facebook, Shopee và YouTube.

## Nhạc nền không bản quyền

`tao_nhac.py` tự tổng hợp một bản nhạc ngũ cung phong cách Tết: tiếng gảy như đàn tranh, bass trầm và mõ gõ nhịp. Nhạc tự tạo nên không vướng bản quyền.

```bash
pip install numpy
python tao_nhac.py nhac_tet.m4a --seconds 20 --bpm 104
```

## Nạp kịch bản từ tài liệu kế hoạch tuần

Các file `kich_ban/tuan_*.json` được app nạp tự động khi mở, mỗi kịch bản một lần (xoá đi sẽ không bị nạp lại, cập nhật app không ghi đè kịch bản đã sửa). Tạo file cho tuần mới từ tài liệu "Kịch bản video tuần …" (dạng bảng Mốc / Phần / Lời thoại / Hình ảnh):

```bash
python tools/parse_ke_hoach_doc.py doc.xml kich_ban/tuan_2026_10_12.json --batch tuan-2026-10-12
```

`doc.xml` là nội dung tài liệu ở dạng XML (trường `data.xml` khi đọc tài liệu bằng Claude Docs).
