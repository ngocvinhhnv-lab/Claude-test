"""Dự báo số lượng cần đặt xưởng / nhập hàng cho từng mã.

Cách tính (mỗi mã hàng):
  Tốc độ bán      = SL bán trong N ngày gần nhất / N  × hệ số mùa vụ
  Nhu cầu         = Tốc độ bán × (thời gian xưởng giao + số ngày muốn dự trữ)
  Hàng an toàn    = Nhu cầu × % an toàn
  Cần đặt         = Nhu cầu + Hàng an toàn − Tồn kho   (làm tròn lên theo lô tối thiểu)
  Số ngày còn bán = Tồn kho / Tốc độ bán

Ví dụ:
  python3 -m tools.du_bao_nhap_hang --ban ban_hang.xlsx --ton ton_kho.xlsx \\
      --thoi-gian-giao 20 --du-tru 45 --he-so 2.5
"""
import argparse
import math
import re
from collections import defaultdict
from datetime import timedelta

from tools.doc_file import doc_bang, doc_ngay, doc_so, khong_dau
from tools.xuat_excel import ghi_sheet, tao_file

# So khớp nguyên từ: tránh nhầm "Hoàn thành" (hoan) hay "vận chuyển" (chuyen chứa "huy")
LA_DON_HUY = re.compile(r"\b(huy|cancel\w*|tra hang|hoan tien)\b")

# Thứ tự ưu tiên khi sắp xếp kết quả
HET_HANG, DAT_GAP, CAN_DAT, DU_HANG, TON_CHAM = (
    "HẾT HÀNG", "Đặt gấp", "Cần đặt", "Đủ hàng", "Tồn chậm (không bán)",
)
_THU_TU = {HET_HANG: 0, DAT_GAP: 1, CAN_DAT: 2, DU_HANG: 3, TON_CHAM: 4}
_MAU = {HET_HANG: "do", DAT_GAP: "do", CAN_DAT: "cam", DU_HANG: "xanh", TON_CHAM: "xam"}


def doc_ban_hang(duong_dan):
    """Trả về (danh sách (ngày, mã, tên, SL), số dòng bỏ qua vì huỷ/trả)."""
    ket_qua, bo_qua = [], 0
    for d in doc_bang(duong_dan, ["ngay", "ma", "so_luong"]):
        tt = khong_dau(d.get("trang_thai") or "")
        if LA_DON_HUY.search(tt):
            bo_qua += 1
            continue
        ngay, ma = doc_ngay(d["ngay"]), str(d["ma"] or "").strip()
        if ngay is None or not ma:
            continue
        ket_qua.append((ngay, ma, str(d.get("ten") or "").strip(), doc_so(d["so_luong"])))
    return ket_qua, bo_qua


def doc_ton_kho(duong_dan):
    """Trả về {mã: (tên, tồn)}; cộng dồn nếu một mã xuất hiện nhiều dòng (nhiều kho)."""
    ton = {}
    for d in doc_bang(duong_dan, ["ma", "ton"]):
        ma = str(d["ma"] or "").strip()
        if not ma:
            continue
        ten_cu, sl_cu = ton.get(ma, ("", 0.0))
        ton[ma] = (ten_cu or str(d.get("ten") or "").strip(), sl_cu + doc_so(d["ton"]))
    return ton


def du_bao(ban_hang, ton_kho, so_ngay=30, thoi_gian_giao=15, du_tru=30,
           he_so=1.0, an_toan=0.2, lo_toi_thieu=1, ngay_chot=None):
    """Tính đề xuất nhập hàng. Trả về danh sách dict đã sắp xếp theo mức ưu tiên."""
    if ngay_chot is None:
        ngay_chot = max((n for n, *_ in ban_hang), default=None)
    tu_ngay = ngay_chot - timedelta(days=so_ngay - 1) if ngay_chot else None
    tu_ngay_7 = ngay_chot - timedelta(days=6) if ngay_chot else None

    ban_ky, ban_7, ten = defaultdict(float), defaultdict(float), {}
    for ngay, ma, t, sl in ban_hang:
        if t:
            ten.setdefault(ma, t)
        if tu_ngay <= ngay <= ngay_chot:
            ban_ky[ma] += sl
            if ngay >= tu_ngay_7:
                ban_7[ma] += sl
    for ma, (t, _) in ton_kho.items():
        if t:
            ten.setdefault(ma, t)

    ket_qua = []
    for ma in set(ban_ky) | set(ton_kho):
        ton = ton_kho.get(ma, ("", 0.0))[1]
        tb_ngay = ban_ky[ma] / so_ngay
        toc_do = tb_ngay * he_so
        nhu_cau = toc_do * (thoi_gian_giao + du_tru)
        hang_an_toan = nhu_cau * an_toan
        can = max(0.0, nhu_cau + hang_an_toan - ton)
        can_dat = math.ceil(can / lo_toi_thieu) * lo_toi_thieu if can > 0 else 0
        so_ngay_con = ton / toc_do if toc_do > 0 else None
        # xu hướng: tốc độ 7 ngày gần nhất so với trung bình cả kỳ
        xu_huong = (ban_7[ma] / 7) / tb_ngay - 1 if tb_ngay > 0 and so_ngay > 7 else None

        if toc_do == 0:
            trang_thai = TON_CHAM if ton > 0 else DU_HANG
        elif ton <= 0:
            trang_thai = HET_HANG
        elif so_ngay_con < thoi_gian_giao:
            trang_thai = DAT_GAP
        elif can_dat > 0:
            trang_thai = CAN_DAT
        else:
            trang_thai = DU_HANG

        ket_qua.append({
            "ma": ma, "ten": ten.get(ma, ""), "ban_ky": ban_ky[ma], "ban_7": ban_7[ma],
            "tb_ngay": tb_ngay, "xu_huong": xu_huong, "toc_do": toc_do, "ton": ton,
            "so_ngay_con": so_ngay_con, "nhu_cau": nhu_cau, "can_dat": can_dat,
            "trang_thai": trang_thai,
        })
    ket_qua.sort(key=lambda r: (_THU_TU[r["trang_thai"]], -r["can_dat"], -r["ban_ky"]))
    return ket_qua


def xuat_excel(ket_qua, duong_dan, thong_so):
    cot = [
        ("Mã hàng", 16), ("Tên hàng", 42), ("Trạng thái", 18),
        (f"Bán {thong_so['Số ngày tính trung bình']} ngày", 11), ("Bán 7 ngày", 10),
        ("TB/ngày", 9), ("Xu hướng 7 ngày", 11), ("Tốc độ dự báo/ngày", 12),
        ("Tồn kho", 10), ("Số ngày còn bán", 11), ("Nhu cầu", 10), ("CẦN ĐẶT", 11),
    ]
    dong = [[
        r["ma"], r["ten"], r["trang_thai"], r["ban_ky"], r["ban_7"],
        round(r["tb_ngay"], 2), r["xu_huong"], round(r["toc_do"], 2), r["ton"],
        round(r["so_ngay_con"], 1) if r["so_ngay_con"] is not None else None,
        round(r["nhu_cau"]), r["can_dat"],
    ] for r in ket_qua]
    dinh_dang = {3: "#,##0", 4: "#,##0", 6: "+0%;-0%;0%", 8: "#,##0", 10: "#,##0", 11: "#,##0"}

    def ghi_de_xuat(ws):
        ghi_sheet(ws, cot, dong, dinh_dang, lambda d: _MAU[d[2]])

    def ghi_thong_so(ws):
        ghi_sheet(ws, [("Thông số", 34), ("Giá trị", 16)], [[k, v] for k, v in thong_so.items()])

    return tao_file(duong_dan, [("Đề xuất nhập", ghi_de_xuat), ("Thông số", ghi_thong_so)])


def main(argv=None):
    p = argparse.ArgumentParser(description="Dự báo số lượng cần nhập hàng / đặt xưởng.")
    p.add_argument("--ban", required=True, help="File bán hàng chi tiết (cột: ngày, mã hàng, số lượng)")
    p.add_argument("--ton", help="File tồn kho (cột: mã hàng, tồn kho). Bỏ trống = coi tồn bằng 0")
    p.add_argument("--so-ngay", type=int, default=30, help="Số ngày gần nhất để tính trung bình (mặc định 30)")
    p.add_argument("--thoi-gian-giao", type=int, default=15, help="Số ngày từ lúc đặt đến lúc hàng về (mặc định 15)")
    p.add_argument("--du-tru", type=int, default=30, help="Muốn đủ hàng bán thêm bao nhiêu ngày sau khi hàng về (mặc định 30)")
    p.add_argument("--he-so", type=float, default=1.0, help="Hệ số mùa vụ, vd 2.5 = mùa Tết bán gấp 2,5 lần (mặc định 1)")
    p.add_argument("--an-toan", type=float, default=20, help="%% hàng dự phòng thêm (mặc định 20)")
    p.add_argument("--lo-toi-thieu", type=int, default=1, help="Làm tròn số đặt lên bội số này, vd 50 (mặc định 1)")
    p.add_argument("--ngay-chot", help="Ngày chốt số liệu dd/mm/yyyy (mặc định: ngày mới nhất trong file)")
    p.add_argument("--xuat", default="ket_qua/de_xuat_nhap_hang.xlsx", help="File Excel kết quả")
    a = p.parse_args(argv)

    ban_hang, bo_qua = doc_ban_hang(a.ban)
    if not ban_hang:
        p.error(f"{a.ban}: không đọc được dòng bán hàng nào có ngày và mã hàng hợp lệ.")
    ton_kho = doc_ton_kho(a.ton) if a.ton else {}
    ngay_chot = doc_ngay(a.ngay_chot) if a.ngay_chot else max(n for n, *_ in ban_hang)

    ket_qua = du_bao(ban_hang, ton_kho, a.so_ngay, a.thoi_gian_giao, a.du_tru,
                     a.he_so, a.an_toan / 100, a.lo_toi_thieu, ngay_chot)
    thong_so = {
        "Ngày chốt số liệu": ngay_chot.strftime("%d/%m/%Y"),
        "Số ngày tính trung bình": a.so_ngay,
        "Thời gian xưởng giao (ngày)": a.thoi_gian_giao,
        "Dự trữ sau khi hàng về (ngày)": a.du_tru,
        "Hệ số mùa vụ": a.he_so,
        "% an toàn": a.an_toan,
        "Lô tối thiểu": a.lo_toi_thieu,
        "File bán hàng": a.ban,
        "File tồn kho": a.ton or "(không có — coi tồn = 0)",
        "Dòng bỏ qua (huỷ/trả)": bo_qua,
    }
    xuat_excel(ket_qua, a.xuat, thong_so)

    dem = defaultdict(int)
    for r in ket_qua:
        dem[r["trang_thai"]] += 1
    print(f"Đã phân tích {len(ket_qua)} mã hàng (chốt ngày {thong_so['Ngày chốt số liệu']}).")
    for tt in _THU_TU:
        if dem[tt]:
            print(f"  {tt:<22} {dem[tt]:>5} mã")
    print(f"Tổng cần đặt: {sum(r['can_dat'] for r in ket_qua):,.0f} sản phẩm")
    if not a.ton:
        print("Lưu ý: chưa có file tồn kho nên đang coi tồn = 0.")
    print(f"Kết quả: {a.xuat}")


if __name__ == "__main__":
    main()
