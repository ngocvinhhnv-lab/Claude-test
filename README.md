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

## 4. Bộ dựng báo cáo thị trường TikTok — `tools/bao_cao_tiktok/`

Dựng trang "Thị trường [ngành] TikTok" từ dữ liệu quét FastMoss + video TikTok trong chưa tới 1 giây: 5 nhóm, ma trận cơ hội, top SP kèm video/KOC, shop, thương hiệu nhà, so sánh với lần quét trước. Claude chỉ cần đọc bản tóm tắt ~20 KB để viết nhận định. Xem [HUONG_DAN.md](tools/bao_cao_tiktok/HUONG_DAN.md).

```bash
python3 -m tools.bao_cao_tiktok.chay --nganh tranh_lich --du-lieu du_lieu/tranh_lich/2026-10-10 --truoc du_lieu/tranh_lich/2026-09-26
```

## 5. Làm maket lịch — `app/maket-lich.html`

Mở file Photoshop (.psd) hoặc ảnh (.jpg, .png) của tờ lịch, thay logo, tên công ty, địa chỉ, điện thoại, email của từng khách rồi xuất maket để gửi khách duyệt. Chạy hoàn toàn trên trình duyệt, file không gửi đi đâu.

Cách dùng: mở `app/maket-lich.html` bằng Chrome/Edge (để nguyên thư mục `app/thu-vien/` bên cạnh).

1. **File thiết kế**: kéo file PSD vào. Phần mềm đọc từng lớp (layer), gồm cả hiệu ứng thường dùng: đổ bóng, viền chữ, phủ màu, phủ chuyển màu vàng kim, mặt nạ, clipping.
2. **Thông tin khách**: nhập tên, địa chỉ, điện thoại, email, chọn logo. Logo nền trắng được tự xoá nền. Ô để trống thì dòng đó ẩn đi.
3. **Lớp trong file**: phần mềm tự đoán lớp chữ nào là tên, địa chỉ, điện thoại… theo tên lớp và nội dung. Chữ mới giữ nguyên phông, cỡ, màu, căn lề, hiệu ứng của lớp cũ; dài quá thì tự thu nhỏ cho vừa. “Khuôn chữ” giữ phần nhãn, ví dụ `Điện thoại: {}`.
4. **Khung thông tin như mẫu**: với file ảnh JPG/PNG hoặc PSD không có lớp chữ, bật mục này để vẽ khung logo trái, tên to ở giữa, địa chỉ, dòng ĐT trái và Email phải. Chọn nền “Che kín thông tin cũ” để phủ header cũ có sẵn trong ảnh.
5. **Phông chữ**: máy thiếu phông của file PSD thì tải file .ttf/.otf lên.

Xuất: **JPG/PNG** đủ độ phân giải, **Ảnh nhẹ gửi Zalo** (1600 px), **PSD** giữ nguyên các lớp với chữ và logo đã thay, có thể bật chữ chìm “MAKET CHỜ DUYỆT”.

Tab **Làm hàng loạt**: nạp file Excel/CSV (cột Tên công ty, Địa chỉ, Điện thoại, Email, Website, Logo) hoặc dán từ Excel, chọn nhiều file logo (tên file trùng tên công ty hoặc cột Logo thì tự ghép), bấm “Tạo maket” rồi tải cả loạt về một file .zip.

Giới hạn: file PSB (file lớn), 16-bit, và lớp điều chỉnh màu (Adjustment Layer) chưa hỗ trợ; hiệu ứng Bevel, Inner Shadow, Pattern chưa vẽ; file CMYK đọc được nhưng màu trên màn hình là quy đổi gần đúng. Nút “Bản gốc” hiện ảnh gộp Photoshop lưu trong file để so. Safari/iPhone giới hạn kích thước canvas nên file quá lớn nên xuất trên máy tính.

Thư viện đọc PSD: [ag-psd](https://github.com/Agamnentzar/ag-psd) 31.0.2 (MIT), bản trong `app/thu-vien/ag-psd.js` được sửa một dòng để mở được file CMYK.

## Chạy test

```bash
python3 -m unittest -v
```
