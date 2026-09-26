import tempfile
import unittest
from datetime import date
from pathlib import Path

from openpyxl import Workbook

from tools.doc_file import doc_bang, doc_ngay, doc_so, khong_dau
from tools.du_bao_nhap_hang import (
    CAN_DAT, DAT_GAP, DU_HANG, HET_HANG, TON_CHAM, doc_ban_hang, du_bao,
)
from tools.loi_nhuan import tinh


class TestDocFile(unittest.TestCase):
    def test_khong_dau(self):
        self.assertEqual(khong_dau("  Mã   Hàng Hoá "), "ma hang hoa")
        self.assertEqual(khong_dau("Đơn giá"), "don gia")

    def test_doc_so(self):
        self.assertEqual(doc_so("1.200"), 1200)
        self.assertEqual(doc_so("1,200"), 1200)
        self.assertEqual(doc_so("₫120.000"), 120000)
        self.assertEqual(doc_so("1.234.567,5"), 1234567.5)
        self.assertEqual(doc_so("2,5"), 2.5)
        self.assertEqual(doc_so(None), 0)
        self.assertEqual(doc_so(7), 7)

    def test_doc_ngay(self):
        self.assertEqual(doc_ngay("25/09/2026 14:30:00"), date(2026, 9, 25))
        self.assertEqual(doc_ngay("2026-09-25"), date(2026, 9, 25))
        self.assertIsNone(doc_ngay("abc"))

    def test_bo_qua_dong_ten_bao_cao(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append(["BÁO CÁO BÁN HÀNG"])
            ws.append([])
            ws.append(["Thời gian", "Mã hàng", "Số lượng"])
            ws.append(["01/09/2026", "A", 3])
            wb.save(p)
            self.assertEqual(doc_bang(p, ["ngay", "ma", "so_luong"]),
                             [{"ngay": "01/09/2026", "ma": "A", "so_luong": 3}])

    def test_thieu_cot_bao_loi(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.csv"
            p.write_text("Cột lạ,Khác\n1,2\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                doc_bang(p, ["ma", "ton"])


class TestDuBao(unittest.TestCase):
    def test_loc_don_huy_theo_nguyen_tu(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ban.csv"
            p.write_text(
                "Ngày đặt hàng;SKU phân loại hàng;Số lượng;Trạng thái đơn hàng\n"
                "01/09/2026;A;1;Hoàn thành\n"
                "01/09/2026;A;2;Đang vận chuyển\n"
                "01/09/2026;A;4;Đã hủy\n"
                "01/09/2026;A;8;Trả hàng/Hoàn tiền\n",
                encoding="utf-8",
            )
            dong, bo_qua = doc_ban_hang(p)
            self.assertEqual(sum(sl for *_, sl in dong), 3)
            self.assertEqual(bo_qua, 2)

    def test_tinh_so_can_dat(self):
        chot = date(2026, 9, 30)
        ban = [(date(2026, 9, n), "A", "Hàng A", 2) for n in range(1, 31)]  # 2/ngày
        kq = du_bao(ban, {"A": ("", 50)}, so_ngay=30, thoi_gian_giao=10, du_tru=20,
                    he_so=1.5, an_toan=0.2, lo_toi_thieu=1, ngay_chot=chot)[0]
        # tốc độ 3/ngày; nhu cầu 3×30 = 90; +20% = 108; −50 tồn = 58
        self.assertAlmostEqual(kq["toc_do"], 3)
        self.assertEqual(kq["can_dat"], 58)
        self.assertEqual(kq["trang_thai"], CAN_DAT)

    def test_lam_tron_lo_va_trang_thai(self):
        chot = date(2026, 9, 30)
        ban = [(date(2026, 9, n), m, "", 1) for n in range(1, 31) for m in "ABC"]
        ban.append((date(2026, 8, 1), "D", "", 5))  # ngoài kỳ tính
        ton = {"A": ("", 0), "B": ("", 5), "C": ("", 1000), "D": ("", 10)}
        kq = {r["ma"]: r for r in du_bao(ban, ton, so_ngay=30, thoi_gian_giao=10,
                                          du_tru=20, lo_toi_thieu=50, ngay_chot=chot)}
        self.assertEqual(kq["A"]["trang_thai"], HET_HANG)
        self.assertEqual(kq["A"]["can_dat"], 50)  # cần 36 -> lô 50
        self.assertEqual(kq["B"]["trang_thai"], DAT_GAP)  # còn 5 ngày < 10 ngày giao
        self.assertEqual(kq["C"]["trang_thai"], DU_HANG)
        self.assertEqual(kq["D"]["trang_thai"], TON_CHAM)


class TestLoiNhuan(unittest.TestCase):
    PHI = {"phi_co_dinh_pct": 10, "phi_thanh_toan_pct": 5, "phi_dich_vu_pct": 5,
           "quang_cao_pct": 0, "thue_pct": 0, "phi_moi_don_vnd": 3000, "dong_goi_vnd": 2000}

    def test_tinh_lai(self):
        r = tinh(50000, 100000, self.PHI, bien_muc_tieu=20)
        self.assertAlmostEqual(r["tong_phi_pct"], 20)
        self.assertAlmostEqual(r["tien_phi"], 25000)
        self.assertAlmostEqual(r["lai"], 25000)
        self.assertAlmostEqual(r["bien_pct"], 25)
        self.assertEqual(r["gia_hoa_von"], 69000)   # 55000 / 0.8 = 68750
        self.assertEqual(r["gia_de_xuat"], 92000)   # 55000 / 0.6 = 91667

    def test_bien_muc_tieu_khong_the_dat(self):
        r = tinh(50000, 100000, self.PHI, bien_muc_tieu=80)
        self.assertIsNone(r["gia_de_xuat"])


if __name__ == "__main__":
    unittest.main()
