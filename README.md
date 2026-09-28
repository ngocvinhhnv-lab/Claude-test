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
2. **Khổ in & thông số file**: chọn khổ thành phẩm (A4, A3, 35×50, 40×60, A2, 50×70, 60×90 cm hoặc tự nhập), tràn lề, vùng an toàn. Ảnh lệch tỉ lệ khổ thì chọn “Cắt cho vừa khổ” hoặc “Thu vào khổ, thêm nền”. Bảng thông số cho biết kích thước px/cm, **DPI thực khi in** (đạt/tạm được/thấp), hệ màu, số lớp, phông chữ; bản xem có đường xén (đỏ) và vùng an toàn (xanh), chữ/logo sát mép được cảnh báo. File PSD xuất ra ghi đúng DPI theo khổ.
3. **Thông tin khách**: mỗi dòng có nhãn (ví dụ “Hotline: ”) và nội dung; kéo ⠿ (hoặc phím mũi tên trên nút kéo) để **đổi thứ tự**, maket tự xếp lại. **+ Thêm dòng** / “Thêm nhanh” (Hotline, Zalo, Fanpage, MST, Chi nhánh, Slogan): với PSD, dòng thêm tự lấy kiểu chữ của file và xếp bên dưới; có thể kéo lại vị trí trên maket. Logo nền trắng được tự xoá nền. Ô trống thì dòng đó ẩn.
4. **Lớp trong file**: phần mềm tự đoán lớp chữ nào là chỗ ghi thông tin theo tên lớp và nội dung. Các chỗ ghi được điền lần lượt theo thứ tự dòng (trên xuống, trái sang phải). Chữ mới giữ nguyên phông, cỡ, màu, căn lề, hiệu ứng; dài quá thì tự thu nhỏ.
5. **Khung thông tin doanh nghiệp**: với file ảnh JPG/PNG hoặc PSD không có lớp chữ, phần mềm dựng **nhóm lớp riêng “Thông tin doanh nghiệp”** (dải nền, logo, đường kẻ, mỗi dòng thông tin một lớp chữ). **Bấm đúp vào chữ trên maket để sửa trực tiếp**, Enter để xuống dòng (Ctrl+Enter hoặc bấm ra ngoài để lưu, Esc để huỷ); nội dung sửa được ghi ngược về mục Thông tin khách. Kéo từng dòng, đổi cỡ, màu riêng từng dòng; thêm hàng hay xuống dòng thì các dòng bên dưới và dải nền tự dạt theo, vẫn giữ phần đã chỉnh tay. Xuất PSD giữ nguyên nhóm lớp này (lớp chữ thật, sửa tiếp bằng Photoshop); nút **PNG thông tin** xuất riêng phần thông tin nền trong suốt.
   - **AI thiết kế** tự chọn bố cục (6 kiểu), phông, phối màu hợp với tranh; **Chọn lại** ra phương án khác, các phương án được giữ để quay lại. **Làm theo maket mẫu**: PSD mẫu thì chép đúng vị trí, cỡ, phông, màu, hiệu ứng; ảnh mẫu thì AI đọc bố cục.
   - **Kết nối AI**: chọn Claude (có sẵn khi mở trên claude.ai), **Google Gemini** hoặc **OpenAI ChatGPT** và dán API key (lấy tại aistudio.google.com/apikey hoặc platform.openai.com/api-keys), có nút kiểm tra kết nối. Key chỉ lưu trong trình duyệt của máy đó. Trang trên claude.ai chặn kết nối ra ngoài nên Gemini/ChatGPT chỉ dùng được ở bản mở từ file trên máy. Không có AI thì phần mềm tự phối theo màu tranh.
6. **Phông chữ**: bấm **Dùng phông cài trên máy** (Chrome/Edge, bản mở từ file trên máy) để lấy toàn bộ phông Windows đang cài (UTM, SVN, VNI…); chữ trên maket vẽ đúng phông của file PSD, các ô chọn phông liệt kê phông máy, và PSD xuất ra ghi đúng tên PostScript để Photoshop nhận đúng phông. Máy thiếu phông nào thì tải file .ttf/.otf lên.
7. **Bảng quy cách trên maket duyệt**: thêm dải dưới maket gồm khách hàng, sản phẩm, khổ, chất liệu, gia công, số lượng, ngày giao, đơn vị thực hiện và ô “Khách hàng duyệt” để ký.

**Bloc lịch · xem cân đối**: tải ảnh bloc, nhập kích thước (cm), bloc hiện đúng tỉ lệ trên maket, kéo để thử vị trí (tự hút vào tâm), báo khoảng cách tới các mép, độ lệch tâm, bloc có đè lên chữ thông tin hay không. Bloc chỉ để xem, không in vào file xuất.

**Sửa chi tiết trên maket** (thanh công cụ trên khung xem trước):

- **Chọn & kéo**: bấm vào chi tiết bất kỳ (chữ, hoa, câu đối, bloc lịch…) để chọn, kéo để di chuyển; phím mũi tên dịch từng px (giữ Shift: 10 px), Delete để ẩn. Cũng chọn được bằng cách bấm tên lớp ở mục 3.
- Bảng sửa của chi tiết đang chọn: ẩn, sửa nội dung chữ (ví dụ đổi “2027” thành “2028”), đổi màu chữ, thay ảnh của lớp, đổi cỡ (20–300%), độ đậm, dịch ngang/dọc, đặt lại.
- **Xoá vùng**: kéo khung quanh chỗ cần bỏ. “Lấp bằng màu xung quanh” dùng được cả cho ảnh JPG phẳng (ví dụ xoá header cũ in sẵn trong ảnh); “Xoá trong suốt” khoét trống trên lớp PSD.
- **Hoàn tác** từng bước. Mọi chỉnh sửa được áp cho cả xuất JPG/PNG và file PSD.

Xuất: **JPG/PNG** đủ độ phân giải, **Ảnh nhẹ gửi Zalo** (1600 px), **PSD** giữ nguyên các lớp với chữ và logo đã thay, có thể bật chữ chìm “MAKET CHỜ DUYỆT”.

Giới hạn: file PSB (file lớn), 16-bit, và lớp điều chỉnh màu (Adjustment Layer) chưa hỗ trợ; hiệu ứng Bevel, Inner Shadow, Pattern chưa vẽ; file CMYK đọc được nhưng màu trên màn hình là quy đổi gần đúng. Nút “Bản gốc” hiện ảnh gộp Photoshop lưu trong file để so. Safari/iPhone giới hạn kích thước canvas nên file quá lớn nên xuất trên máy tính.

**Xuất PSD** dựng một file mới hoàn toàn (RGB 8-bit, đúng khổ và DPI), không ghi lại dữ liệu gốc như smart object, shape, hiệu ứng, profile màu — vì chỉ một khối ghi sai là Photoshop từ chối cả file. Mỗi chi tiết là một lớp ảnh (đã gộp hiệu ứng, mặt nạ, clipping), giữ tên lớp, nhóm, độ mờ, chế độ hoà trộn. Chọn “PSD: chữ thông tin sửa được” thì mỗi dòng thông tin (và chữ đã sửa) thành nhóm gồm lớp bóng/viền (ảnh), lớp chữ thật, và lớp màu vàng kim/chuyển màu clipping vào chữ, sửa chữ trong Photoshop vẫn giữ màu. “PSD: toàn bộ là ảnh” chỉ có lớp ảnh và nhóm. Lớp điều chỉnh màu (Adjustment) không được xuất.

Thư viện đọc PSD: [ag-psd](https://github.com/Agamnentzar/ag-psd) 31.0.2 (MIT), bản trong `app/thu-vien/ag-psd.js` được sửa một dòng để mở được file CMYK.

## Chạy test

```bash
python3 -m unittest -v
```
