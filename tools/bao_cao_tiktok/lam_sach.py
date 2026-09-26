"""Đọc dữ liệu một lượt quét, lọc đúng ngành, chia nhóm và ngách theo file cấu hình."""
import json
import re
import unicodedata
from pathlib import Path


def N(s):
    """Bỏ dấu, chữ thường, gộp khoảng trắng: 'Lịch Tết' -> 'lich tet'."""
    s = str(s or "").replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().lower()


def doc_cau_hinh(ten_hoac_duong_dan):
    p = Path(ten_hoac_duong_dan)
    if not p.suffix:
        p = Path(__file__).with_name("cau_hinh") / f"{ten_hoac_duong_dan}.json"
    ch = json.loads(p.read_text(encoding="utf-8"))
    ch["_file"] = str(p)
    return ch


def _doc_json(thu_muc, ten, mac_dinh=None):
    p = Path(thu_muc) / ten
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else mac_dinh


def _gop_video_tho(tho, ids):
    """Dữ liệu video thô của bộ quét (__sv.V: {video_id: {d,t,pl,u,fo,p:[sp_id,...]}}) -> dạng tổng hợp."""
    from datetime import datetime, timezone
    theo_sp = {}
    for vid, o in tho.items():
        p = o.get("p")
        if not p or str(p[0]) not in ids:
            continue
        theo_sp.setdefault(str(p[0]), []).append((vid, o))
    kq = {}
    for sp, ds in theo_sp.items():
        ds.sort(key=lambda x: -(x[1].get("pl") or 0))
        koc = {}
        for vid, o in ds:
            k = koc.setdefault(o.get("u") or "?", [o.get("u") or "?", 0, 0, 0])
            k[1] += o.get("pl") or 0
            k[2] = max(k[2], o.get("fo") or 0)
            k[3] += 1

        def ngay(t):
            try:
                return datetime.fromtimestamp(int(t), timezone.utc).strftime("%d/%m/%y")
            except (TypeError, ValueError):
                return ""
        kq[sp] = {
            "n": len(ds), "xem": sum(o.get("pl") or 0 for _, o in ds), "koc": len(koc),
            "v": [[vid, o.get("u", ""), o.get("pl") or 0, ngay(o.get("t")), re.sub(r"[\ud800-\udfff]", "", str(o.get("d") or ""))[:28]] for vid, o in ds[:10]],
            "k": sorted(koc.values(), key=lambda k: -k[1])[:10],
        }
    return {"tong_video": len(tho), "video_gan_sp": sum(1 for o in tho.values() if o.get("p")), "sp": kq}


def doc_luot_quet(thu_muc):
    """Đọc thư mục một lượt quét. Chỉ fastmoss.json là bắt buộc."""
    thu_muc = Path(thu_muc)
    fm = _doc_json(thu_muc, "fastmoss.json")
    if fm is None:
        raise FileNotFoundError(f"Thiếu {thu_muc / 'fastmoss.json'}")
    video = _doc_json(thu_muc, "video.json")
    if video is None and (tho := _doc_json(thu_muc, "video_tho.json")) is not None:
        video = _gop_video_tho(tho, set(fm))
    return {
        "fastmoss": fm,
        "video": video or {"sp": {}},
        "co_video": video is not None,
        "tu_khoa": _doc_json(thu_muc, "tu_khoa.json", []),
        "nhan_dinh": _doc_json(thu_muc, "nhan_dinh.json", {}),
        "thong_tin": _doc_json(thu_muc, "thong_tin.json", {}),
    }


def _re(p):
    return re.compile(p) if p else None


class PhanLoai:
    def __init__(self, ch):
        loc = ch["loc"]
        self.hang_muc = {N(h) for h in loc.get("hang_muc", [])}
        self.phai_co, self.loai = _re(loc.get("phai_co")), _re(loc.get("loai"))
        self.ban_min = loc.get("ban_toi_thieu_28_ngay", 1)
        self.luat_nhom = [(r["nhom"], _re(r.get("khop")), _re(r.get("tru"))) for r in ch["luat_nhom"]]
        self.luat_ngach = [(r["ten"], r.get("nhom"), _re(r.get("khop")), _re(r.get("tru"))) for r in ch["ngach"]]
        self.nha = _re(ch.get("shop_nha", {}).get("khop"))
        self.nha_xac_nhan = {N(s) for s in ch.get("shop_nha", {}).get("da_xac_nhan", [])}

    def ly_do_loai(self, r):
        """None nếu giữ; nếu loại trả về lý do ngắn."""
        t = N(r.get("t"))
        if (r.get("s28") or 0) < self.ban_min:
            return "không bán trong 28 ngày"
        c = r.get("c")
        if c and self.hang_muc and not ({N(x) for x in str(c).split("|")} & self.hang_muc):
            return f"hạng mục ngoài ngành ({c})"
        if self.phai_co and not self.phai_co.search(t):
            return "tên không có từ khoá ngành"
        if self.loai and (m := self.loai.search(t)):
            return f"hàng nhiễu ({m.group(0).strip()})"
        return None

    def nhom(self, t):
        t = N(t)
        for ma, khop, tru in self.luat_nhom:
            if (khop is None or khop.search(t)) and not (tru and tru.search(t)):
                return ma
        return None

    def ngach(self, t, nhom):
        t = N(t)
        for ten, chi_nhom, khop, tru in self.luat_ngach:
            if chi_nhom and chi_nhom != nhom:
                continue
            if (khop is None or khop.search(t)) and not (tru and tru.search(t)):
                return ten
        return "Khác"

    def la_nha(self, shop):
        """'xac_nhan' | 'nghi' | None."""
        if N(shop) in self.nha_xac_nhan:
            return "xac_nhan"
        if self.nha and self.nha.search(str(shop or "").lower()):
            return "nghi"
        return None


def lam_sach(luot, ch):
    """Trả về (danh sách SP đã lọc + gắn nhóm/ngách, danh sách SP bị loại kèm lý do)."""
    pl = PhanLoai(ch)
    giu, loai = [], []
    for pid, r in luot["fastmoss"].items():
        # SP tách từ báo cáo cũ đã được lọc; listing nhà 0 đơn vẫn giữ để báo "listing 0 đơn"
        ly_do = None if r.get("_tai_dung") else pl.ly_do_loai(r)
        if ly_do == "không bán trong 28 ngày" and pl.la_nha(r.get("sh")):
            ly_do = None
        if ly_do:
            loai.append({"id": pid, "t": r.get("t"), "sh": r.get("sh"), "ly_do": ly_do, "s28": r.get("s28")})
            continue
        sp = dict(r)
        sp["id"] = str(pid)
        if r.get("_tai_dung") and r.get("_g"):
            # dữ liệu tách từ báo cáo cũ: giữ nhãn gốc để dựng lại đúng bản cũ
            sp["nhom"], sp["ngach"] = r["_g"], r.get("_n") or pl.ngach(r.get("t"), r["_g"])
        else:
            sp["nhom"] = pl.nhom(r.get("t"))
            sp["ngach"] = pl.ngach(r.get("t"), sp["nhom"])
        sp["nha"] = pl.la_nha(r.get("sh"))
        v = luot["video"].get("sp", {}).get(sp["id"]) or {}
        sp["vid_n"], sp["vid_xem"], sp["vid_koc"] = v.get("n", 0), v.get("xem", 0), v.get("koc", 0)
        sp["vid_top"], sp["koc_top"] = v.get("v", []), v.get("k", [])
        giu.append(sp)
    return giu, loai
