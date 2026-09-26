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

## Chạy test

```bash
python3 -m unittest -v
```
