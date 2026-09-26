# Tạo nhiều video từ 1 video gốc

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

`defaults` áp dụng cho mọi video. Tuỳ chọn đặt trong từng video sẽ ghi đè lên `defaults`.

| Tuỳ chọn | Ý nghĩa | Mặc định |
|---|---|---|
| `clips` | Các đoạn cần lấy, nhiều đoạn thì ghép nối. Dạng `["0:05","0:20"]`, `"0:05-0:20"`, `"end"` = hết video | cả video |
| `ratio` | `9:16`, `1:1`, `4:5`, `16:9`, `original`, hoặc danh sách để xuất nhiều khung | `9:16` |
| `fit` | `blur` (nền mờ), `crop` (cắt tràn khung), `pad` (viền đen) | `blur` |
| `speed` | Tốc độ, ví dụ `1.25` hoặc `0.5` | `1.0` |
| `text` / `text_pos` | Chữ hiện suốt video, vị trí `top` / `center` / `bottom` | — / `top` |
| `captions` | Chữ theo thời gian: `[{"start":0,"end":3,"text":"..."}]`, tính theo giây của video xuất ra | — |
| `logo` / `logo_pos` / `logo_size` | Ảnh logo (PNG nền trong), góc đặt, kích thước so với cạnh ngắn | — / `top-right` / `0.18` |
| `music` / `music_volume` | Nhạc nền (tự lặp nếu ngắn hơn video), âm lượng | — / `0.3` |
| `keep_audio` | Giữ tiếng gốc khi có nhạc nền | `true` |
| `fade` | Số giây fade in/out cho hình và tiếng | `0` |
| `fps`, `crf`, `font` | Số khung hình/giây, chất lượng (càng nhỏ càng nét), phông chữ | `30`, `20`, `DejaVu Sans` |

Video xuất ra ở dạng MP4 (H.264 + AAC), dùng được cho TikTok, Facebook, Shopee và YouTube.
