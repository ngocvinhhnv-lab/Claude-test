"""Test bộ dựng báo cáo TikTok bằng dữ liệu GIẢ (tên shop, số liệu đều bịa)."""
import json
import tempfile
import unittest
from pathlib import Path

from tools.bao_cao_tiktok import tach_bao_cao_cu
from tools.bao_cao_tiktok.chay import chay
from tools.bao_cao_tiktok.chi_so import tinh, xu_huong
from tools.bao_cao_tiktok.dung_trang import gon, so
from tools.bao_cao_tiktok.lam_sach import _gop_video_tho, doc_cau_hinh, doc_luot_quet, lam_sach

HM = "Đồ treo trang trí"


def sp(t, sh, s28, a28, s7, tr=None, c=HM, s=None, v=10, lt="2026-06-01"):
    return {"t": t, "sh": sh, "sid": "", "c": c, "p": a28 / s28 if s28 else 50000, "s": s if s is not None else s28 * 3,
            "v": v, "a": 3, "s7": s7, "s28": s28, "a28": a28, "a7": None, "tr": tr or [s7 // 7] * 7, "lt": lt, "k": ["x"]}


def du_lieu_gia():
    fm = {
        "1001": sp("Tranh Nề Nếp Gia Đình treo tường phòng khách", "Tường Vip", 500, 33_000_000, 200, [10, 12, 15, 30, 40, 45, 48]),
        "1002": sp("Tranh bố mẹ gửi con liễn canvas", "Shop Alpha", 800, 52_000_000, 150, [40, 30, 25, 20, 15, 10, 10]),
        "1003": sp("Tranh những điều bố mẹ ít nói quy tắc gia đình", "Shop Beta", 120, 8_000_000, 20),
        "1004": sp("Bảng thời khóa biểu tráng gương tặng bút", "Shop Gamma", 1000, 90_000_000, 150, c="Đồ dùng học tập & giáo dục"),
        "1005": sp("Bảng thời khóa biểu 3 trong 1", "Nhà Sách Newshop", 300, 25_000_000, 40, c="Đồ dùng học tập & giáo dục"),
        "1006": sp("Lịch để bàn mini 2027 có lịch âm", "Shop Delta", 200, 7_000_000, 120, c="Lịch & Phụ kiện"),
        "1007": sp("Bloc lịch Tết 2027 bloc đại phong thủy", "Tường Vip", 40, 3_600_000, 25, c="Lịch & Phụ kiện"),
        "1008": sp("Khung ảnh tráng gương in ảnh theo yêu cầu 40x60", "Shop Epsilon", 900, 110_000_000, 260),
        "1009": sp("Tranh Phật Di Lặc túi tiền treo tường", "Shop Zeta", 400, 50_000_000, 20),
        "1010": sp("Tranh dán tường set 6 tấm decor phòng khách", "Shop Eta", 600, 24_000_000, 170),
        "1011": sp("Tranh laminate tráng gương hoa sen", "Tường Vip", 0, 0, 0),           # nhà, 0 đơn -> giữ
        "1012": sp("Tranh treo tường chữ Phúc", "Tranh Lịch Newshop", 50, 4_000_000, 10),  # tên giống nhà, chưa xác nhận
        # hàng nhiễu
        "2001": sp("Tóc giả nữ tết lệch", "Shop Hair", 900, 90_000_000, 200, c="Tóc giả"),
        "2002": sp("Sticker tranh dán laptop", "Shop Stick", 300, 3_000_000, 50),
        "2003": sp("Tranh xếp hình puzzle 1000 mảnh", "Shop Toy", 300, 30_000_000, 50),
        "2004": sp("Tranh Nề Nếp bản cũ", "Shop Alpha", 0, 0, 0),                           # 0 đơn, không phải nhà
        "2005": sp("Áo thun in hình", "Shop Tee", 500, 50_000_000, 100),                   # không có từ khoá ngành
    }
    tho = {  # video thô kiểu __sv.V
        "9001": {"d": "Review tranh nề nếp", "t": 1757000000, "pl": 50000, "u": "koc_a", "fo": 1200, "p": ["1001", "Tranh", "1"]},
        "9002": {"d": "Tranh cho phòng khách", "t": 1757100000, "pl": 150000, "u": "koc_b", "fo": 9000, "p": ["1001", "Tranh", "1"]},
        "9003": {"d": "Mở hộp", "t": 1757200000, "pl": 7000, "u": "koc_a", "fo": 1300, "p": ["1001", "Tranh", "1"]},
        "9004": {"d": "Thời khoá biểu", "t": 1757300000, "pl": 90000, "u": "koc_c", "fo": 500, "p": ["1004", "TKB", "2"]},
        "9005": {"d": "Không gắn SP", "t": 1757300000, "pl": 1_000_000, "u": "koc_d", "fo": 1, "p": None},
        "9006": {"d": "SP ngoài báo cáo", "t": 1757300000, "pl": 5, "u": "koc_e", "fo": 1, "p": ["7777", "x", "3"]},
    }
    tt = {"ngay_quet": "10/10/2026", "ngay_chot": "09/10/2026", "tu_khoa_fastmoss": 12, "luot_tim_fastmoss": 14,
          "tu_khoa_video": 5, "tong_video": 6}
    nd = {"ket_luan": [{"tieu_de": "Điều A", "noi_dung": "Xem [listing](https://shop.tiktok.com/vn/pdp/1001)."}],
          "viec_nen_lam": [{"nhan": "Gia đình · làm ngay", "tieu_de": "Việc B", "vi_sao": "Vì C", "lam_gi": "Làm D", "danh_doi": "E"}]}
    tk = [{"tu": "lịch mini", "luot": "2k+", "hang_muc": "Lịch", "tren_ke": 0, "tin_hieu": "Nhu cầu chưa đáp ứng"}]
    return fm, tho, tt, nd, tk


def ghi(thu_muc, fm, tho=None, tt=None, nd=None, tk=None):
    thu_muc = Path(thu_muc)
    thu_muc.mkdir(parents=True, exist_ok=True)
    for ten, v in [("fastmoss.json", fm), ("video_tho.json", tho), ("thong_tin.json", tt), ("nhan_dinh.json", nd), ("tu_khoa.json", tk)]:
        if v is not None:
            (thu_muc / ten).write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
    return thu_muc


class TestLamSach(unittest.TestCase):
    def setUp(self):
        self.ch = doc_cau_hinh("tranh_lich")
        self.tmp = tempfile.TemporaryDirectory()
        fm, tho, tt, nd, tk = du_lieu_gia()
        self.luot = doc_luot_quet(ghi(self.tmp.name, fm, tho, tt, nd, tk))
        self.ds, self.loai = lam_sach(self.luot, self.ch)
        self.by = {s["id"]: s for s in self.ds}

    def tearDown(self):
        self.tmp.cleanup()

    def test_loc_hang_nhieu(self):
        ly_do = {x["id"]: x["ly_do"] for x in self.loai}
        self.assertEqual(set(ly_do), {"2001", "2002", "2003", "2004", "2005"})
        self.assertIn("hạng mục", ly_do["2001"])
        self.assertIn("sticker", ly_do["2002"])
        self.assertIn("xep hinh", ly_do["2003"])
        self.assertEqual(ly_do["2004"], "không bán trong 28 ngày")

    def test_giu_listing_nha_0_don(self):
        self.assertIn("1011", self.by)
        self.assertEqual(self.by["1011"]["nha"], "xac_nhan")
        self.assertEqual(self.by["1012"]["nha"], "nghi")

    def test_chia_nhom_ngach(self):
        mong = {"1001": ("giadinh", "Nề nếp & bố mẹ gửi con"), "1004": ("be", "Thời khóa biểu"),
                "1006": ("lich", "Lịch để bàn"), "1007": ("lich", "Bloc & lịch Tết"),
                "1008": ("guong", "In ảnh theo yêu cầu"), "1009": ("guong", "Phật & tôn giáo"),
                "1010": ("decor", "Set tranh dán tường")}
        for pid, (g, n) in mong.items():
            self.assertEqual((self.by[pid]["nhom"], self.by[pid]["ngach"]), (g, n), self.by[pid]["t"])

    def test_gop_video_tho(self):
        v = self.by["1001"]
        self.assertEqual((v["vid_n"], v["vid_xem"], v["vid_koc"]), (3, 207000, 2))
        self.assertEqual([x[0] for x in v["vid_top"]], ["9002", "9001", "9003"])
        self.assertEqual(v["koc_top"][0], ["koc_b", 150000, 9000, 1])
        self.assertEqual(v["koc_top"][1], ["koc_a", 57000, 1300, 2])
        tong = _gop_video_tho(du_lieu_gia()[1], {"1001", "1004"})
        self.assertEqual((tong["tong_video"], tong["video_gan_sp"]), (6, 5))


class TestChiSo(unittest.TestCase):
    def setUp(self):
        self.ch = doc_cau_hinh("tranh_lich")
        self.tmp = tempfile.TemporaryDirectory()
        fm, tho, tt, nd, tk = du_lieu_gia()
        self.luot = doc_luot_quet(ghi(self.tmp.name, fm, tho, tt, nd, tk))
        self.ds, _ = lam_sach(self.luot, self.ch)
        self.M = tinh(self.ds, self.luot, self.ch)
        self.nhom = {g["ma"]: g for g in self.M["nhom"]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_kpi(self):
        k = self.M["kpi"]
        self.assertEqual(k["sp"], 12)
        self.assertEqual(k["don28"], 500 + 800 + 120 + 1000 + 300 + 200 + 40 + 900 + 400 + 600 + 0 + 50)

    def test_nhom_gia_dinh(self):
        g = self.nhom["giadinh"]
        self.assertEqual((g["sp"], g["don28"], g["don7"]), (3, 1420, 370))
        self.assertAlmostEqual(g["nhip"], 370 * 4 / 1420)
        self.assertAlmostEqual(g["top3"], 1.0)  # chỉ có 3 shop
        self.assertAlmostEqual(self.nhom["guong"]["top3"], (110 + 50) / (110 + 50 + 0))
        self.assertEqual(g["shop_lon"][0][0], "Shop Alpha")
        self.assertEqual(g["khung_chinh"], "50–100k (100%)")  # giá TB 65–67k

    def test_hang_va_xu_huong(self):
        by = {s["id"]: s for s in self.ds}
        self.assertEqual((by["1002"]["hang"], by["1001"]["hang"]), (1, 2))
        self.assertEqual(by["1001"]["xh"], "tăng")
        self.assertEqual(by["1002"]["xh"], "giảm")
        self.assertIsNone(xu_huong([5, 5, 5, 5, 5, 5, 5]))

    def test_nha_va_van_de(self):
        self.assertEqual({s["ten"] for s in self.M["nha_shop"]}, {"Tường Vip", "Nhà Sách Newshop"})
        loai = sorted(v["loai"] for v in self.M["van_de_nha"])
        self.assertEqual(loai, ["khong_don", "nghi"])

    def test_so_sanh_lan_truoc(self):
        truoc = [dict(s) for s in self.ds]
        for s in truoc:
            if s["id"] == "1003":
                s["s28"] = 5000  # lần trước 1003 dẫn nhóm
        M = tinh(self.ds, self.luot, self.ch, truoc)
        ss = M["so_sanh"]
        self.assertEqual(ss["thay_doi"]["1003"]["hang"], 1)
        self.assertEqual(ss["nhom"]["giadinh"]["don28"], 1420 - 120 + 5000)
        self.assertEqual(ss["vao_top"], [])  # nhóm nhỏ: mọi SP vẫn trong top 10


class TestDungTrang(unittest.TestCase):
    def test_dinh_dang(self):
        self.assertEqual(gon(9_441_599_821), "9,44 tỷ")
        self.assertEqual(gon(812_862_076), "812,9 tr")
        self.assertEqual(gon(32_454), "32k")
        self.assertEqual(gon(9_990), "9.990")
        self.assertEqual(so(1_234_567), "1.234.567")

    def test_dung_va_tach_nguoc(self):
        """Dựng trang từ dữ liệu giả rồi tách ngược lại: số liệu phải khớp."""
        fm, tho, tt, nd, tk = du_lieu_gia()
        with tempfile.TemporaryDirectory() as d:
            thu_muc = ghi(Path(d) / "a", fm, tho, tt, nd, tk)
            M, ra, _ = chay("tranh_lich", thu_muc)
            trang = (ra / "bao_cao.html").read_text(encoding="utf-8")
            for pane in ['id="tq"', 'id="top"', 'id="all"', 'id="shop"', 'id="nha"', 'id="vid"', 'id="cach"']:
                self.assertIn(pane, trang)
            self.assertIn("Chưa đủ ngách", trang)  # dữ liệu giả chỉ có 1 ngách đủ 3 SP
            self.assertIn('<a href="https://shop.tiktok.com/vn/pdp/1001"', trang)  # link trong nhận định
            tom = json.loads((ra / "tom_tat.json").read_text(encoding="utf-8"))
            self.assertEqual(tom["kpi"]["sp"], 12)
            self.assertIn("Tóc giả nữ", (ra / "kiem_tra.txt").read_text(encoding="utf-8"))

            kq = tach_bao_cao_cu.tach(ra / "bao_cao.html")
            self.assertEqual(set(kq["fastmoss"]), {s["id"] for s in M["theo_nhom"]["giadinh"] + sum((M["theo_nhom"][g] for g in M["theo_nhom"] if g != "giadinh"), [])})
            self.assertEqual(sum(r["s28"] for r in kq["fastmoss"].values()), M["kpi"]["don28"])
            self.assertEqual(sum(r["a28"] for r in kq["fastmoss"].values()), M["kpi"]["dt28"])
            self.assertEqual(kq["fastmoss"]["1004"]["_g"], "be")
            self.assertEqual(kq["video"]["sp"]["1001"]["n"], 3)
            self.assertEqual([v[0] for v in kq["video"]["sp"]["1001"]["v"]], ["9002", "9001", "9003"])
            self.assertEqual(kq["video"]["sp"]["1001"]["k"][0][0], "koc_b")
            self.assertEqual(kq["nhan_dinh"]["ket_luan"][0]["noi_dung"], nd["ket_luan"][0]["noi_dung"])
            self.assertEqual(kq["tu_khoa"][0]["tu"], "lịch mini")
            self.assertEqual(kq["thong_tin"]["ngay_chot"], "09/10/2026")

            # lần quét sau so với lần này
            fm2 = json.loads(json.dumps(fm))
            fm2["1003"]["s28"] = 2000
            thu_muc2 = ghi(Path(d) / "b", fm2, tho, tt)
            M2, ra2, _ = chay("tranh_lich", thu_muc2, truoc=thu_muc)
            self.assertEqual(M2["so_sanh"]["thay_doi"]["1003"]["don28"], 120)
            self.assertIn("So với lần quét trước", (ra2 / "bao_cao.html").read_text(encoding="utf-8"))
            self.assertIn("Chưa có nhận định", (ra2 / "bao_cao.html").read_text(encoding="utf-8"))


@unittest.skipUnless(Path("du_lieu/tranh_lich/2026-09-26/fastmoss.json").exists(), "không có dữ liệu thật 26/09 (không đưa lên git)")
class TestDuLieuThat(unittest.TestCase):
    """Chỉ chạy trên máy có dữ liệu thật: so với số trong báo cáo 26/09 đã đăng."""

    def test_khop_bao_cao_26_09(self):
        ch = doc_cau_hinh("tranh_lich")
        luot = doc_luot_quet("du_lieu/tranh_lich/2026-09-26")
        ds, _ = lam_sach(luot, ch)
        M = tinh(ds, luot, ch)
        self.assertEqual((M["kpi"]["sp"], M["kpi"]["shop"], M["kpi"]["don28"]), (208, 128, 128826))
        g = {x["ma"]: x for x in M["nhom"]}
        self.assertEqual(g["giadinh"]["don28"], 12393)
        self.assertEqual(round(g["guong"]["top3"], 3), 0.396)
        self.assertEqual(g["lich"]["khung_chinh"], "Dưới 50k (85%)")
        # luật (không dùng nhãn cũ) phải khớp phần lớn nhãn trong báo cáo
        for r in luot["fastmoss"].values():
            r["_tai_dung"] = False
        ds2, _ = lam_sach(luot, ch)
        khop = sum(s["nhom"] == s["_g"] for s in ds2) / len(ds2)
        self.assertGreaterEqual(khop, 0.95)


if __name__ == "__main__":
    unittest.main()
