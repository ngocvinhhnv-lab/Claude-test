# Bộ dựng báo cáo "Thị trường [ngành] TikTok"

Thay cho việc viết `build.py` mới mỗi lần làm báo cáo. Dữ liệu vào là một thư mục, ra là trang HTML để đăng và một bản tóm tắt gọn cho Claude viết nhận định.

## Quy trình mỗi lần làm báo cáo

1. **Lấy số** như trước (skill `tiktok-shop-research`), rồi lưu vào `du_lieu/<ngành>/<yyyy-mm-dd>/`:
   - `fastmoss.json`: đổ nguyên `localStorage.__FM` của extractor FastMoss. Đây là **file bắt buộc duy nhất**.
   - `video_tho.json`: nguyên dữ liệu `__sv.V` (IndexedDB `vidsave`). Cũng có thể dùng `video.json` đã tổng hợp theo mục 7 của skill.
   - `tu_khoa.json` (Seller Center) và `thong_tin.json` (ngày quét, ngày chốt, số từ khoá, ghi chú lỗi). Hai file này không bắt buộc.
2. **Dựng bản 1** (mất khoảng 0,2 giây):
   ```bash
   python3 -m tools.bao_cao_tiktok.chay --nganh tranh_lich --du-lieu du_lieu/tranh_lich/2026-10-10 \
       --truoc du_lieu/tranh_lich/2026-09-26 --bao-cao-cu <file trang đang đăng>.html
   ```
   - `--truoc`: so với lần quét trước (SP mới vào hoặc rời top 10, đơn thay đổi). Không bắt buộc.
   - `--bao-cao-cu`: giữ nguyên các tab do skill khác làm (40 đối thủ thắng, Đối thủ & kịch bản, KOC xếp hạng). Danh sách tab giữ lại nằm ở `tab_giu_lai` trong file cấu hình.
3. **Soát nhanh** `ket_qua/kiem_tra.txt`: SP bị loại, SP chưa vào ngách nào, mẫu tên từng ngách. Nếu xếp sai, sửa regex trong `cau_hinh/<ngành>.json` rồi chạy lại. Không cần sửa code.
4. **Claude chỉ đọc `ket_qua/tom_tat.json`** (khoảng 20 KB) rồi viết `nhan_dinh.json` (mẫu bên dưới) vào thư mục dữ liệu. Chạy lại bước 2.
5. **Đăng** `ket_qua/bao_cao.html` lên đúng link cũ (Artifact `url`). Các file CSV đã đăng kèm vẫn được giữ.

## Mẫu `nhan_dinh.json`

Trong văn bản, link viết dạng `[chữ](https://...)`.

```json
{
  "ket_luan": [
    {"tieu_de": "Hàng học đường vừa qua đỉnh", "noi_dung": "Nhóm tranh cho bé ... [SP số 1](https://shop.tiktok.com/vn/pdp/...) ..."}
  ],
  "viec_nen_lam": [
    {"nhan": "Tranh gia đình · làm ngay", "tieu_de": "Đẩy tranh Nề Nếp lên số 1",
     "vi_sao": "...", "lam_gi": "...", "danh_doi": "..."}
  ]
}
```

## Thêm ngành mới (ví dụ trà)

Sao chép `cau_hinh/tranh_lich.json` thành `cau_hinh/tra.json`, rồi sửa các phần sau: tiêu đề, `loc` (hạng mục, regex phải có và regex loại), `nhom` và `luat_nhom`, `ngach`, màu. Chạy với `--nganh tra`.

## Chỉ còn trang báo cáo, mất dữ liệu gốc?

```bash
python3 -m tools.bao_cao_tiktok.tach_bao_cao_cu trang_bao_cao.html du_lieu/tranh_lich/2026-09-26
```

Lệnh này tách số liệu, video/KOC top, từ khoá và nhận định từ trang đã đăng. Kết quả dùng được làm `--truoc` cho lần sau. Đơn từng ngày được ước lại từ hình sparkline nên chỉ đúng hình dạng.

## Lưu ý

- Repo đang **công khai**: thư mục `du_lieu/` nằm trong `.gitignore`, **không đưa số liệu thật lên GitHub**.
- Công thức tính giữ đúng skill `tiktok-bao-cao-nganh` mục 3 và 4: nhịp 7 ngày = đơn 7 ngày × 4 / đơn 28 ngày; giá TB = doanh thu 28 ngày / đơn 28 ngày; xu hướng tính bằng 3 ngày cuối so với 3 ngày đầu (±30%); ma trận dùng trục log, trung vị, bỏ ngách dưới 3 SP.
- Kiểm tra: `python3 -m unittest tests.test_bao_cao_tiktok`.
