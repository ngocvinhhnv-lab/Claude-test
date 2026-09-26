"""Dựng báo cáo "Thị trường [ngành] TikTok" từ một thư mục dữ liệu quét.

  python3 -m tools.bao_cao_tiktok.chay --nganh tranh_lich --du-lieu du_lieu/tranh_lich/2026-10-10 \\
      [--truoc du_lieu/tranh_lich/2026-09-26] [--bao-cao-cu bao_cao_dang_dang.html]

Thư mục dữ liệu (chỉ fastmoss.json là bắt buộc):
  fastmoss.json   {id: bản ghi FastMoss}          — đúng dạng extractor __FM của skill tiktok-shop-research
  video.json      {"sp": {id: {n, xem, koc, v, k}}} hoặc video_tho.json (dữ liệu __sv.V thô)
  tu_khoa.json    [{tu, luot, hang_muc, tren_ke, tin_hieu}]  — Seller Center
  thong_tin.json  {ngay_quet, ngay_chot, tu_khoa_fastmoss, luot_tim_fastmoss, tu_khoa_video, tong_video, ghi_chu}
  nhan_dinh.json  {ket_luan: [...], viec_nen_lam: [...]}  — phần Claude viết sau khi đọc tom_tat.json

Kết quả ghi vào <du-lieu>/ket_qua/:
  bao_cao.html    trang để đăng
  tom_tat.json    bản tóm tắt gọn cho Claude viết nhận định
  san_pham.json   SP đã làm sạch (lần sau dùng làm --truoc)
  kiem_tra.txt    SP bị loại, SP rơi vào "Khác", mẫu tên từng ngách — để soát luật
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from tools.bao_cao_tiktok.chi_so import tinh, tom_tat
from tools.bao_cao_tiktok.dung_trang import Trang, gon, pct, so, tach_tab_giu
from tools.bao_cao_tiktok.lam_sach import N, doc_cau_hinh, doc_luot_quet, lam_sach


def doc_truoc(thu_muc, ch):
    """SP đã làm sạch của lượt trước: ưu tiên ket_qua/san_pham.json, không có thì làm sạch lại từ dữ liệu thô."""
    p = Path(thu_muc) / "ket_qua" / "san_pham.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    luot = doc_luot_quet(thu_muc)
    ds, _ = lam_sach(luot, ch)
    for s in ds:
        s["_ngay_chot"] = luot["thong_tin"].get("ngay_chot")
    return ds


def kiem_tra(ds, loai, ten_nhom):
    dong = [f"== {len(loai)} SP bị loại =="]
    dong += [f"  [{x['ly_do']}] {x.get('s28') or 0:>6} đơn · {x.get('sh')} · {x.get('t')}" for x in sorted(loai, key=lambda x: -(x.get("s28") or 0))]
    khac = [s for s in ds if s["ngach"] == "Khác" or s["nhom"] is None]
    dong.append(f"\n== {len(khac)} SP chưa vào ngách nào (sửa luật 'ngach' trong cấu hình nếu cần) ==")
    dong += [f"  [{ten_nhom.get(s['nhom'], s['nhom'])}] {s.get('s28')} đơn · {s['t']}" for s in khac]
    theo = defaultdict(list)
    for s in ds:
        theo[(s["nhom"], s["ngach"])].append(s)
    dong.append("\n== Mẫu tên theo nhóm / ngách (tối đa 8, xếp theo đơn 28 ngày) ==")
    for (g, n), lst in sorted(theo.items(), key=lambda x: (str(x[0][0]), x[0][1])):
        dong.append(f"-- {ten_nhom.get(g, g)} / {n}: {len(lst)} SP")
        dong += [f"     {s.get('s28'):>6} · {s['t'][:95]}" for s in sorted(lst, key=lambda s: -(s.get("s28") or 0))[:8]]
    return "\n".join(dong) + "\n"


def _json_sp(ds):
    giu = ["id", "t", "sh", "sid", "c", "p", "s", "v", "a", "s7", "s28", "a28", "tr", "lt", "nhom", "ngach", "nha",
           "vid_n", "vid_xem", "vid_koc", "_ngay_chot"]
    return [{k: s.get(k) for k in giu} for s in ds]


def chay(nganh, du_lieu, truoc=None, bao_cao_cu=None, xuat=None):
    ch = doc_cau_hinh(nganh)
    luot = doc_luot_quet(du_lieu)
    ds, loai = lam_sach(luot, ch)
    if not ds:
        raise ValueError("Không còn SP nào sau khi lọc — kiểm tra lại cấu hình 'loc' hoặc dữ liệu.")
    luot["_loai"] = loai
    for s in ds:
        s["_ngay_chot"] = luot["thong_tin"].get("ngay_chot")
    ds_truoc = doc_truoc(truoc, ch) if truoc else None
    M = tinh(ds, luot, ch, ds_truoc)

    tab_giu, json_giu = [], []
    if bao_cao_cu:
        tab_giu, json_giu = tach_tab_giu(Path(bao_cao_cu).read_text(encoding="utf-8"), ch.get("tab_giu_lai", []))
    trang = Trang(M, luot, ch, tab_giu)
    trang.json_giu = json_giu

    ra = Path(xuat) if xuat else Path(du_lieu) / "ket_qua"
    ra.mkdir(parents=True, exist_ok=True)
    (ra / "bao_cao.html").write_text(trang.html(), encoding="utf-8")
    tt = tom_tat(M, luot, ch)
    (ra / "tom_tat.json").write_text(json.dumps(tt, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (ra / "san_pham.json").write_text(json.dumps(_json_sp(ds), ensure_ascii=False, separators=(",", ":"), default=str), encoding="utf-8")
    (ra / "kiem_tra.txt").write_text(kiem_tra(ds, loai, M["ten_nhom"]), encoding="utf-8")
    return M, ra, tab_giu


def main(argv=None):
    p = argparse.ArgumentParser(description="Dựng báo cáo thị trường ngành TikTok từ dữ liệu quét.")
    p.add_argument("--nganh", required=True, help="Tên file cấu hình trong tools/bao_cao_tiktok/cau_hinh (vd tranh_lich) hoặc đường dẫn .json")
    p.add_argument("--du-lieu", required=True, help="Thư mục dữ liệu của lượt quét")
    p.add_argument("--truoc", help="Thư mục dữ liệu lượt quét trước, để so sánh")
    p.add_argument("--bao-cao-cu", help="Trang báo cáo đang đăng (.html) để giữ lại các tab do skill khác làm")
    p.add_argument("--xuat", help="Thư mục ghi kết quả (mặc định <du-lieu>/ket_qua)")
    a = p.parse_args(argv)
    try:
        M, ra, tab_giu = chay(a.nganh, a.du_lieu, a.truoc, a.bao_cao_cu, a.xuat)
    except (FileNotFoundError, ValueError) as loi:
        print(f"Lỗi: {loi}", file=sys.stderr)
        return 1
    k = M["kpi"]
    print(f"{so(k['sp'])} SP · {so(k['shop'])} shop · {so(k['don28'])} đơn 28 ngày · {gon(k['dt28'])}")
    for g in M["nhom"]:
        print(f"  {g['ten']:<38} {g['sp']:>4} SP {so(g['don28']):>8} đơn  nhịp {pct(g['nhip']):>5}  top 3 shop {pct(g['top3']):>4}")
    if M["so_sanh"]:
        print(f"  So với lần trước: {len(M['so_sanh']['vao_top'])} SP mới vào top 10, {len(M['so_sanh']['roi_top'])} SP rời top 10")
    if tab_giu:
        print(f"  Giữ lại {len(tab_giu)} tab từ báo cáo cũ: {', '.join(n for _, n, _ in tab_giu)}")
    kb = (ra / "tom_tat.json").stat().st_size / 1024
    print(f"Kết quả trong {ra}/: bao_cao.html ({(ra / 'bao_cao.html').stat().st_size / 1e6:.2f} MB), tom_tat.json ({kb:.0f} KB), san_pham.json, kiem_tra.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
