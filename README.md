# Claude-test

Bộ công cụ xử lý số liệu bán hàng. Đọc được file Excel/CSV xuất từ KiotViet, Sapo, Shopee, TikTok Shop; tự bỏ qua các dòng tên báo cáo phía trên và tự nhận diện tên cột.

```bash
pip install -r requirements.txt
python3 -m tools.tao_du_lieu_mau      # tạo file mẫu trong du_lieu_mau/ để chạy thử
```

## 1. Dự báo nhập hàng — `tools/du_bao_nhap_hang.py`

Gợi ý mỗi mã hàng cần đặt xưởng bao nhiêu, mã nào sắp hết, mã nào tồn lâu không bán.

```bash
python3 -m tools.du_bao_nhap_hang \
    --ban ban_hang.xlsx --ton ton_kho.xlsx \
    --thoi-gian-giao 20 --du-tru 45 --he-so 2.5 --lo-toi-thieu 50
```

| Tham số | Ý nghĩa | Mặc định |
|---|---|---|
| `--ban` | File bán hàng chi tiết: cần cột **ngày**, **mã hàng**, **số lượng** | bắt buộc |
| `--ton` | File tồn kho: cần cột **mã hàng**, **tồn kho** (nhiều kho thì cộng dồn) | coi tồn = 0 |
| `--so-ngay` | Lấy trung bình bán bao nhiêu ngày gần nhất | 30 |
| `--thoi-gian-giao` | Từ lúc đặt đến lúc hàng về mất bao nhiêu ngày | 15 |
| `--du-tru` | Hàng về rồi thì muốn đủ bán thêm bao nhiêu ngày | 30 |
| `--he-so` | Hệ số mùa vụ, ví dụ Tết bán gấp 2,5 lần thì để `2.5` | 1 |
| `--an-toan` | % hàng dự phòng thêm | 20 |
| `--lo-toi-thieu` | Làm tròn số lượng đặt lên theo lô của xưởng | 1 |
| `--ngay-chot` | Ngày chốt số liệu `dd/mm/yyyy` | ngày mới nhất trong file |

Cách tính:

```
Tốc độ bán   = SL bán trong N ngày / N × hệ số mùa vụ
Cần đặt      = Tốc độ × (thời gian giao + dự trữ) × (1 + % an toàn) − Tồn kho
```

Đơn có trạng thái *huỷ*, *trả hàng*, *hoàn tiền* được tự loại ra. Kết quả được sắp theo mức ưu tiên và tô màu: **HẾT HÀNG** / **Đặt gấp** (tồn không đủ bán tới lúc hàng về) → **Cần đặt** → **Đủ hàng** → **Tồn chậm**.

## 2. Tính lợi nhuận — `tools/loi_nhuan.py`

Tính lãi thực mỗi đơn sau phí sàn, giá hoà vốn, và giá bán cần đặt để đạt biên lãi mong muốn, cho từng kênh.

```bash
# Một sản phẩm
python3 -m tools.loi_nhuan --gia-von 38000 --gia-ban 89000

# Hàng loạt: file cần cột giá vốn, giá bán (thêm mã hàng, tên hàng nếu có)
python3 -m tools.loi_nhuan --file san_pham.xlsx --bien-muc-tieu 20 --kenh shopee tiktok
```

> ⚠️ Biểu phí trong `tools/cau_hinh_phi.json` hiện là **số ví dụ**. Hãy sửa theo phí thực tế của từng shop (phí cố định theo ngành hàng, phí thanh toán, Freeship/Voucher Xtra, quảng cáo, thuế). Có thể thêm kênh mới bằng cách thêm một mục vào file này.

Kết quả Excel có mỗi kênh một sheet, tô màu: đỏ = lỗ, vàng = lãi dưới mục tiêu, xanh = đạt.

## 3. Ứng dụng web — `app/so-kho-lai.html`

Bản chạy trên trình duyệt của cả hai công cụ trên (cùng cách tính): kéo thả file Excel/CSV là ra kết quả, tải về Excel được. Biểu phí sàn lưu chung cho mọi người dùng, chỉ người có quyền Chỉnh sửa mới đổi được.

## 4. Xưởng ảnh AI — `app/xuong-anh-ai.html`

Nâng cấp từ "Bảng mẫu brief ảnh AI": 20 mẫu ấn phẩm (post, story, banner, packshot, poster, KOC…) kèm checklist và prompt tiếng Việt tự điền theo brief, nay bấm **Tạo ảnh** là ra ảnh ngay trong trang.

| Công cụ tạo ảnh | Chạy ở đâu | Cần gì |
|---|---|---|
| Canva AI | Trang mở trong Claude (claude.ai) | Đã kết nối Canva trong Settings → Connectors |
| Gemini (Nano Banana) | Mở file trên máy bằng trình duyệt | API key Google AI Studio |
| OpenAI (GPT Image) | Mở file trên máy bằng trình duyệt | API key OpenAI |

- Chọn tỉ lệ (1:1, 4:5, 9:16, 16:9, 2:3, 4:3, 21:9) và số ảnh (1–4) mỗi lượt.
- Chọn model: OpenAI mặc định GPT Image 2.5 Sunburst (có Flare, GPT Image 2, 1.5, 1 Mini); Gemini mặc định Nano Banana Pro (có Nano Banana 2, 2 Lite). Chọn độ nét 1K/2K/4K và chất lượng (OpenAI).
- Tải lên tối đa 4 ảnh sản phẩm thật (nhiều góc, tự thu nhỏ về 2048 px, nhớ cho lần sau) và ảnh tham chiếu; Gemini/OpenAI nhận các ảnh này để giữ đúng nhãn và phong cách.
- Tải ảnh sản phẩm lên là AI (Claude trong claude.ai, hoặc Gemini/OpenAI bằng key của bạn) tự đọc ảnh, chỉ chọn trong thư viện 3 mẫu hợp nhất, chỉnh prompt của các mẫu đó theo sản phẩm (vẫn giữ chỗ {…} để sửa brief sau), tự điền brief và đưa mẫu hợp nhất lên xưởng. Có Hoàn tác.
- **Sửa tiếp** một ảnh đã tạo: chỉ cần ghi điều muốn đổi.
- Ảnh đã tạo lưu trong trình duyệt (tối đa 60 ảnh), tải về, dùng lại prompt.
- Trong Claude: nút "Phân tích và viết prompt" cho Claude đọc ảnh tham chiếu và viết prompt theo brief.

API key chỉ lưu trong trình duyệt và gửi thẳng tới Google/OpenAI. Trong Claude, trang không gọi được API bên ngoài nên chỉ dùng Canva.

## 5. Bộ dựng báo cáo thị trường TikTok — `tools/bao_cao_tiktok/`

Dựng trang "Thị trường [ngành] TikTok" từ dữ liệu quét FastMoss + video TikTok trong chưa tới 1 giây: 5 nhóm, ma trận cơ hội, top SP kèm video/KOC, shop, thương hiệu nhà, so sánh với lần quét trước. Claude chỉ cần đọc bản tóm tắt ~20 KB để viết nhận định. Xem [HUONG_DAN.md](tools/bao_cao_tiktok/HUONG_DAN.md).

```bash
python3 -m tools.bao_cao_tiktok.chay --nganh tranh_lich --du-lieu du_lieu/tranh_lich/2026-10-10 --truoc du_lieu/tranh_lich/2026-09-26
```

## Chạy test

```bash
python3 -m unittest -v
```
