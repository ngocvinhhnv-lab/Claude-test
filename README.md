# TikTok Video Studio

Ứng dụng web dựng video bán hàng TikTok: **tự quay source → lấy kịch bản từ video đối thủ → lồng giọng tiếng Việt → đầy đủ chữ và phụ đề → xuất video 9:16**.

## Chạy ứng dụng web

Cần **Python 3.10–3.13 (khuyên dùng 3.12)** và **ffmpeg** bản đầy đủ (bản đầy đủ, có `libass` và `zscale`).

| Hệ điều hành | Cài ffmpeg | Chạy app |
|---|---|---|
| Windows | Tải bản "full" tại gyan.dev/ffmpeg, thêm thư mục `bin` vào PATH | Bấm đúp `chay_app.bat` |
| macOS | `brew install ffmpeg` | `./chay_app.sh` |
| Linux | `sudo apt install ffmpeg` | `./chay_app.sh` |

Hướng dẫn từng bước cho nhân viên (Windows): [`HUONG_DAN_WINDOWS.pdf`](HUONG_DAN_WINDOWS.pdf) (nguồn HTML ở `docs/huong_dan_windows/`).

App mở tại http://127.0.0.1:8000. Để máy khác trong mạng nội bộ dùng chung: `./chay_app.sh --host 0.0.0.0`. Dữ liệu (video, kịch bản, video xuất ra) lưu trong thư mục `data/`.

### Cách nhanh: tạo video hàng loạt

Tab **Tạo hàng loạt** (mở sẵn): thả video đã quay, chọn nhiều kịch bản, bấm một nút. App tự làm toàn bộ và dựng lần lượt từng video ở nền:

1. AI mô tả từng đoạn video bạn quay (một lần, kết quả được lưu lại), nên ghép cảnh cho cả chục kịch bản chỉ cần gửi chữ. Cùng lúc đó AI ghi lại đoạn nào **đã có chữ cháy sẵn trong hình** (phụ đề, chữ chèn, giá, tên kênh khác — không tính chữ in trên chính sản phẩm).
2. Mỗi kịch bản được ghép cảnh quay phù hợp (ưu tiên đoạn ít được dùng ở video khác), tạo giọng đọc, chữ, phụ đề, nhạc rồi dựng. Mỗi video là một dự án bình thường nên mở ra chỉnh tay được.
3. **Thư viện kịch bản chỉ để tham khảo.** Cảnh nào chưa có video quay khớp thì app (mặc định) nhờ AI **viết lại cảnh đó cho khớp video đã quay**: chọn đoạn quay có sẵn rồi chỉ nói và chỉ hiện những gì thấy được hoặc thông tin đã có trong kịch bản gốc và ghi chú video, không bịa giá hay thông số. Cảnh đã khớp tốt luôn giữ nguyên lời gốc. Cảnh không thể nói trung thực điều gì thì bị bỏ (trừ mở đầu và chốt). Nếu hơn nửa kịch bản không có video quay cho sản phẩm thì kịch bản được giữ lại với nhãn **Thiếu video quay**. Mọi thay đổi xem được bằng **Xem … cảnh đã viết lại** (lời gốc và lời mới). Có thể tắt ở ô "Khi thiếu cảnh quay phù hợp".
   Kịch bản còn ô `[kiểm tra]` trong lời đọc bị giữ lại để sửa rồi **Tiếp tục**.
4. **Soát lại trước khi dựng** (mặc định bật): AI đọc lại cả kịch bản cùng đoạn quay đã chọn cho từng cảnh và sửa trước khi máy dựng — lời phải đúng thứ đang thấy trong cảnh, mạch phải thuận (mở đầu → chi tiết → chốt), không dùng lại một đoạn hai lần, không nói lặp ý, và **tổng phải ra 30–40 giây** (thiếu thì thêm cảnh từ các đoạn chưa dùng, dư thì cắt). Mọi chỗ sửa hiện trong **Xem … cảnh đã soát lại**. Tắt được ở ô "Soát lại trước khi dựng".
5. **Chữ trên màn hình luôn đi kèm lời đọc:** mỗi cảnh có một cụm chữ ngắn 2–6 từ rút từ chính câu nói của cảnh đó (tắt tiếng vẫn hiểu). Cảnh nào **trong hình đã có người nói với máy quay**, hoặc đã có chữ cháy sẵn, thì app **không chèn chữ**. App cũng tự sửa khi AI đặt nhầm chỗ (câu nói rơi vào ô chữ, ô lời chỉ còn một mẩu như `nu`) và bỏ các mẩu chữ vô nghĩa trước khi dựng.
6. **Video nguồn còn chữ hoặc sticker cũ:** đoạn nào còn **bất cứ** chữ chèn, sticker, watermark, emoji hay nét khoanh của lần dựng trước **bị bỏ hẳn** khỏi kho ghép cảnh (AI xem 3 khung hình đầu–giữa–cuối mỗi đoạn nên chữ chỉ hiện thoáng qua cũng bắt được). App ghi rõ bỏ bao nhiêu đoạn. Chữ **in trên chính sản phẩm** (ngày trên tờ lịch, chữ trên tranh) không tính. Nếu **một phần tư số đoạn trở lên** của cùng một file dính chữ thì app coi cả file là **bản đã dựng rồi** và bỏ hẳn cả file — vì chữ rải khắp file, bắt được đoạn này vẫn sót đoạn kia.

   **Khi không còn đoạn sạch nào, app tự chuyển sang "xào nấu"** thay vì dừng lại: **cắt bỏ hẳn dải có chữ cũ ra khỏi khung hình** (đáy 22% hoặc đỉnh 16%, phần còn lại phóng đầy khung 9:16 nên không lộ viền), đảo lại thứ tự các đoạn, viết lời và chữ mới — ra một video khác hẳn video gốc. Đoạn nào có chữ **nằm giữa khung** thì cắt kiểu gì cũng còn nên vẫn bị bỏ. Ô "Đoạn quay còn chữ hoặc sticker cũ" có ba lựa chọn: *Bỏ hẳn; hết đoạn sạch thì tự xào nấu* (mặc định), *Luôn xào nấu*, và *Vẫn dùng nếu chữ ngắn* (giữ nguyên hình, chỉ **đặt chữ mới tránh chỗ chữ cũ**).
7. **Tải tất cả (ZIP)** gồm các video, `noi_dung_dang.txt` (caption, hashtag, điều cần kiểm tra) và `can_quay_them.txt`.

Tiến độ lưu trong `data/batches`, đóng trình duyệt hay tắt app đều tiếp tục được. Không có API key thì vẫn tạo được video nhưng chỉ ghép cảnh đơn giản.

### Để AI tự viết kịch bản từ video bạn vừa quay

Ở **Bước 2 · Chọn kịch bản**, mở **✨ Để AI xem video bạn vừa thả rồi tự viết kịch bản cho đúng video đó**: chọn số kịch bản (2–5), kênh sẽ đăng và những thông tin được phép nói (giá, khổ, số tờ). AI phân tích từng phân đoạn trong video của bạn rồi viết nhiều kịch bản **khác hướng nhau** (hậu trường, cận cảnh chất liệu, cách dùng, so sánh, lời khuyên) để bạn chọn một cái.

- Mỗi cảnh của kịch bản **gắn sẵn một đoạn quay thật**, nên lời đọc và hình luôn khớp nhau sau khi dựng; đến lượt dựng app dùng đúng đoạn đó, không ghép lại nữa.
- Viết xong, AI **soát lại** từng cảnh một lần nữa (đúng hình chưa, mạch có thuận không, đủ **30–40 giây** chưa) rồi mới đưa vào thư viện.
- Bấm **Xem kịch bản** ngay trong danh sách để đọc trọn kịch bản: ảnh từng đoạn quay, lời đọc, chữ trên màn hình và tổng số giây.
- Lời chỉ nói những gì thấy trong đoạn đã chọn hoặc thông tin bạn ghi ở ô trên — không bịa giá, thông số, đánh giá; không có ô `[kiểm tra]` nào.
- Các đoạn có phụ đề cháy sẵn không phù hợp được loại trước khi viết.
- Kịch bản mới nằm trong thư viện với nhãn **Từ video của bạn**, mở ở tab **1. Kịch bản** để sửa lời, hoặc bấm **Dựng video từ kịch bản này** (các cảnh đã có đoạn, chỉ cần xuất).

### Video quay bằng iPhone (.MOV) và các định dạng khác

App đọc được **.MOV** (kể cả viết hoa `.MOV`), **.MP4, .M4V, .MKV, .AVI, .WEBM, .3GP, .3G2, .MTS, .M2TS, .MPG, .MPEG, .WMV, .FLV**. Video iPhone HDR (HLG) tự được đổi màu về SDR, video quay dọc tự xoay đúng chiều, file có thêm track âm thanh phụ vẫn đọc bình thường.

- **Hộp chọn file khai rõ từng đuôi** (không chỉ "video/*" như trước): Windows hay ẩn file `.mov` khi chỉ khai kiểu chung, nên trước đây có máy không thấy file iPhone trong hộp chọn.
- **Tải từng file một, có phần trăm** (thanh trên cùng hiện `2/16 · IMG_1342.MOV (765 MB) · 40%`). File iPhone nặng cả trăm MB, tải gộp một lần mà đứt giữa chừng là mất sạch; tải riêng thì file nào lỗi chỉ mất file đó, các file còn lại vẫn vào.
- **File không phải video** (ảnh, Word, PDF…) bị bỏ qua và báo tên file; nếu vẫn gửi lên máy chủ thì bị từ chối kèm danh sách đuôi hợp lệ.
- **File hỏng hoặc chép dở** từ điện thoại không làm treo app nữa: video đó hiện nhãn **Lỗi** kèm lý do ngay trong danh sách (trước đây kẹt mãi ở "Đang xử lý"). Chép lại file rồi thả lại.
- **Video 4K nặng chạy nhanh hơn**: dò chuyển cảnh ở khổ nhỏ, làm bản xem thử 30 khung/giây, và video HDR được thu nhỏ **trước** khi đổi màu (đổi màu ở khổ 4K rất chậm), dựng nhanh gần gấp đôi với hình giống hệt.

### Cập nhật thư viện kịch bản

Ở tab **1. Kịch bản** (hoặc nút **+ Nhập kịch bản mới** ở tab Tạo hàng loạt), thẻ **Nhập kịch bản từ file hoặc link**: upload Word, PDF, Excel, HTML, CSV, TXT, MD, JSON, dán link, hoặc dán nội dung. AI tự tách từng kịch bản thành các cảnh. Kịch bản trùng mã được **cập nhật**, không nhân đôi. Lưu ý:

- Cần Anthropic API key (trừ file JSON đúng định dạng của app, nhập thẳng không cần AI).
- Link phải mở được mà không cần đăng nhập. Google Docs/Sheets: chia sẻ "Bất kỳ ai có link" (app tự đổi sang bản tải về). Link cần đăng nhập (Claude, Notion...) thì xuất ra file rồi upload. Chỉ nhận link trên internet, không nhận địa chỉ nội bộ.
- Chữ trong `[...]` được giữ nguyên, AI không tự điền.
- Tài liệu tối đa 200.000 ký tự (PDF 30 MB); dài hơn thì tách file.

### Quy trình từng video (thủ công)

1. **Kịch bản.** Upload video đối thủ (tải từ TikTok về) hoặc dán link TikTok/Facebook (app tự tải bằng yt-dlp, được cập nhật mỗi lần mở app). AI xem khung hình, đọc chữ, nghe lời thoại, rồi tách thành từng cảnh: cảnh quay gì, lời đọc, chữ trên màn hình, độ dài. Sau đó bấm **Viết lại cho sản phẩm của tôi**: AI giữ cấu trúc và nhịp nhưng viết lời mới, không bịa giá hay khuyến mãi. Thư viện có sẵn 3 kịch bản mẫu KB1–KB3 và 40 kịch bản của kế hoạch tuần 05–11/10/2026 (`kich_ban/tuan_2026_10_05.json`), có ô tìm kiếm theo mã, sản phẩm, kênh. Kịch bản còn ô `[kiểm tra]` trong lời đọc sẽ bị chặn xuất video cho tới khi điền thông tin thật.
2. **Video nguồn.** Upload video tự quay, được nhiều file một lúc. App tạo bản xem thử, chia thành các đoạn ngắn và tự chuyển màu video HDR của iPhone.
3. **Dựng video.** Từ kịch bản bấm **Dựng video từ kịch bản này**, rồi:
   - **Chọn cảnh:** bấm **AI ghép cảnh tự động** (AI chọn đoạn nguồn cho từng cảnh và báo cảnh còn thiếu), hoặc tự chọn từng đoạn.
   - **Giọng đọc và nhạc:** chọn giọng, nhạc nền, khung hình.
   - **Xuất:** bấm **Xuất video**.

### Video xuất ra

- **Giọng đọc quyết định nhịp dựng.** Mỗi cảnh dài đúng bằng lời đọc. Nếu đoạn quay ngắn hơn lời, app tự lấy dài thêm trong video nguồn, quay chậm, hoặc giữ khung cuối.
- **Cắt ghép sạch:** mỗi cảnh chỉ lấy trong đúng một cảnh quay (không lẫn cảnh khác), né vài khung hình sát chỗ chuyển cảnh, và kịch bản được viết cho vừa độ dài đoạn quay nên hạn chế phải quay chậm hay giữ khung cuối; cảnh nào vẫn phải kéo quá 1,5 lần thì app báo để xem lại.
- **Chữ đầy đủ:** chữ trên màn hình theo từng cảnh, phụ đề chạy theo lời đọc. Tất cả nằm trong vùng an toàn, không bị thanh tab, cột nút và caption của TikTok che.
- **Phông và màu chữ:** tab Cài đặt cho chọn phông có sẵn trên máy (phông gợi ý có dấu ★), màu chữ và màu phụ đề từ bảng màu đẹp sẵn, kiểu chữ nền hộp mờ hoặc chữ viền, có ô xem trước. Mỗi dự án đổi riêng được ở tab Dựng video. Phông đã chọn được chép kèm khi dựng nên chữ ra đúng trên mọi máy.
- **Nhạc riêng:** upload file nhạc của shop ở tab Cài đặt (hoặc ngay ở Bước 3), dùng lại cho mọi video; vẫn giữ lựa chọn nhạc Tết tự tạo không bản quyền.
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

## Bảo mật và dữ liệu

- Cài đặt (API key giọng đọc và AI) lưu ngoài thư mục `data`: Windows `%APPDATA%\TikTokVideoStudio\settings.json`, macOS/Linux `~/.config/tiktok-video-studio/settings.json` (đổi bằng biến `VIDEO_APP_CONFIG`). Bản cũ để trong `data/` sẽ tự chuyển sang.
- Thư mục `data` chỉ phát ra web các file ảnh, video, âm thanh; file `.json` trả về 404.
- Yêu cầu ghi dữ liệu từ trang web lạ (có `Origin` khác địa chỉ app) bị chặn.
- App không có đăng nhập. Mặc định chỉ mở ở `127.0.0.1`; khi chạy `--host 0.0.0.0` thì chỉ dùng trong mạng nội bộ tin cậy.
- Phông chữ DejaVu Sans đi kèm trong `fonts/` (giấy phép trong `fonts/LICENSE-DejaVu.txt`) nên chữ trong video giống nhau trên mọi máy.

## Kiểm thử

```bash
pip install httpx
python -m unittest discover -s tests -v
```
