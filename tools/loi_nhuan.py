"""Tính lãi thực mỗi đơn sau phí sàn, và giá bán cần đặt để đạt biên lợi nhuận mong muốn.

  Tổng % phí   = phí cố định + phí thanh toán + phí dịch vụ + quảng cáo + thuế   (tính trên giá bán)
  Phí cố định  = phí mỗi đơn + đóng gói                                          (VNĐ/đơn)
  Lãi          = Giá bán × (1 − Tổng % phí) − Giá vốn − Phí cố định
  Giá hoà vốn  = (Giá vốn + Phí cố định) / (1 − Tổng % phí)
  Giá đề xuất  = (Giá vốn + Phí cố định) / (1 − Tổng % phí − Biên mục tiêu)

Ví dụ:
  python3 -m tools.loi_nhuan --gia-von 45000 --gia-ban 99000
  python3 -m tools.loi_nhuan --file san_pham.xlsx --bien-muc-tieu 20
"""
import argparse
import json
import math
from pathlib import Path

from tools.doc_file import doc_bang, doc_so
from tools.xuat_excel import ghi_sheet, tao_file

FILE_PHI = Path(__file__).with_name("cau_hinh_phi.json")
_CAC_PCT = ("phi_co_dinh_pct", "phi_thanh_toan_pct", "phi_dich_vu_pct", "quang_cao_pct", "thue_pct")


def doc_cau_hinh(duong_dan=FILE_PHI):
    with open(duong_dan, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def lam_tron_len(so, buoc=1000):
    return math.ceil(so / buoc) * buoc


def tinh(gia_von, gia_ban, phi, bien_muc_tieu=20.0):
    """phi: một mục trong cau_hinh_phi.json. Trả về dict kết quả (tiền VNĐ, % dạng 0–100)."""
    tong_pct = sum(phi.get(k, 0) for k in _CAC_PCT) / 100
    co_dinh = phi.get("phi_moi_don_vnd", 0) + phi.get("dong_goi_vnd", 0)
    tien_phi = gia_ban * tong_pct + co_dinh
    lai = gia_ban - tien_phi - gia_von
    mau_hoa_von = 1 - tong_pct
    mau_de_xuat = 1 - tong_pct - bien_muc_tieu / 100
    return {
        "gia_von": gia_von,
        "gia_ban": gia_ban,
        "tong_phi_pct": tong_pct * 100,
        "tien_phi": tien_phi,
        "lai": lai,
        "bien_pct": lai / gia_ban * 100 if gia_ban else None,
        "gia_hoa_von": lam_tron_len((gia_von + co_dinh) / mau_hoa_von) if mau_hoa_von > 0 else None,
        # None = phí + biên mục tiêu ≥ 100%, không có giá nào đạt được
        "gia_de_xuat": lam_tron_len((gia_von + co_dinh) / mau_de_xuat) if mau_de_xuat > 0 else None,
    }


def _mau(bien, muc_tieu):
    if bien is None or bien < 0:
        return "do"
    return "cam" if bien < muc_tieu else "xanh"


def tinh_file(duong_dan, cau_hinh, bien_muc_tieu, xuat):
    san_pham = [
        (str(d.get("ma") or "").strip(), str(d.get("ten") or "").strip(),
         doc_so(d["gia_von"]), doc_so(d["gia_ban"]))
        for d in doc_bang(duong_dan, ["gia_von", "gia_ban"])
    ]
    san_pham = [sp for sp in san_pham if sp[3] > 0]
    cot = [
        ("Mã hàng", 14), ("Tên hàng", 40), ("Giá vốn", 11), ("Giá bán", 11), ("Tổng % phí", 9),
        ("Tiền phí/đơn", 11), ("Lãi/đơn", 11), ("Biên lãi", 9), ("Giá hoà vốn", 11),
        (f"Giá để lãi {bien_muc_tieu:g}%", 12),
    ]
    dinh_dang = {2: "#,##0", 3: "#,##0", 4: '0.0"%"', 5: "#,##0", 6: "#,##0",
                 7: '0.0"%"', 8: "#,##0", 9: "#,##0"}
    tom_tat, cac_sheet = [], []
    for kenh, phi in cau_hinh.items():
        dong = []
        for ma, ten, gia_von, gia_ban in san_pham:
            r = tinh(gia_von, gia_ban, phi, bien_muc_tieu)
            dong.append([ma, ten, gia_von, gia_ban, r["tong_phi_pct"], r["tien_phi"], r["lai"],
                         r["bien_pct"], r["gia_hoa_von"], r["gia_de_xuat"]])
        so_lo = sum(1 for d in dong if d[6] < 0)
        so_duoi = sum(1 for d in dong if 0 <= d[7] < bien_muc_tieu)
        tom_tat.append((kenh, len(dong), so_lo, so_duoi))
        cac_sheet.append((kenh.capitalize(), lambda ws, dong=dong: ghi_sheet(
            ws, cot, dong, dinh_dang, lambda d: _mau(d[7], bien_muc_tieu))))
    tao_file(xuat, cac_sheet)
    print(f"Đã tính {len(san_pham)} sản phẩm trên {len(cau_hinh)} kênh (biên mục tiêu {bien_muc_tieu:g}%).")
    for kenh, tong, lo, duoi in tom_tat:
        print(f"  {kenh:<8} lỗ: {lo:>4} mã | lãi dưới mục tiêu: {duoi:>4} mã | đạt: {tong - lo - duoi:>4} mã")
    print(f"Kết quả: {xuat}")


def in_mot_san_pham(gia_von, gia_ban, cau_hinh, bien_muc_tieu):
    print(f"Giá vốn {gia_von:,.0f}đ | Giá bán {gia_ban:,.0f}đ | Biên mục tiêu {bien_muc_tieu:g}%\n")
    print(f"{'Kênh':<9}{'% phí':>7}{'Tiền phí':>11}{'Lãi/đơn':>11}{'Biên':>8}{'Hoà vốn':>11}{'Giá đề xuất':>13}")
    for kenh, phi in cau_hinh.items():
        r = tinh(gia_von, gia_ban, phi, bien_muc_tieu)
        hoa_von = f"{r['gia_hoa_von']:,.0f}" if r["gia_hoa_von"] else "không có"
        de_xuat = f"{r['gia_de_xuat']:,.0f}" if r["gia_de_xuat"] else "không đạt"
        print(f"{kenh:<9}{r['tong_phi_pct']:>6.1f}%{r['tien_phi']:>11,.0f}{r['lai']:>11,.0f}"
              f"{r['bien_pct']:>7.1f}%{hoa_von:>11}{de_xuat:>13}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Tính lợi nhuận sau phí sàn và giá bán đề xuất.")
    p.add_argument("--gia-von", type=float, help="Giá vốn 1 sản phẩm (VNĐ)")
    p.add_argument("--gia-ban", type=float, help="Giá bán (VNĐ)")
    p.add_argument("--file", help="File sản phẩm (cột: mã hàng, tên hàng, giá vốn, giá bán) để tính hàng loạt")
    p.add_argument("--kenh", nargs="+", help="Chỉ tính các kênh này, vd: shopee tiktok")
    p.add_argument("--bien-muc-tieu", type=float, default=20, help="Biên lãi mong muốn %% (mặc định 20)")
    p.add_argument("--cau-hinh", default=str(FILE_PHI), help="File biểu phí (mặc định tools/cau_hinh_phi.json)")
    p.add_argument("--xuat", default="ket_qua/loi_nhuan.xlsx", help="File Excel kết quả (khi dùng --file)")
    a = p.parse_args(argv)

    cau_hinh = doc_cau_hinh(a.cau_hinh)
    if a.kenh:
        sai = [k for k in a.kenh if k not in cau_hinh]
        if sai:
            p.error(f"Không có kênh {sai} trong {a.cau_hinh}. Các kênh: {list(cau_hinh)}")
        cau_hinh = {k: cau_hinh[k] for k in a.kenh}

    if a.file:
        tinh_file(a.file, cau_hinh, a.bien_muc_tieu, a.xuat)
    elif a.gia_von is not None and a.gia_ban:
        in_mot_san_pham(a.gia_von, a.gia_ban, cau_hinh, a.bien_muc_tieu)
    else:
        p.error("Cần --gia-von và --gia-ban, hoặc --file.")


if __name__ == "__main__":
    main()
