"""Tính mọi chỉ số của báo cáo từ danh sách SP đã làm sạch."""
import math
import re
from collections import defaultdict
from datetime import date, datetime

from tools.bao_cao_tiktok.lam_sach import N


def gia_tb(sp):
    """Giá khách thực trả = doanh thu 28 ngày / đơn 28 ngày."""
    return sp["a28"] / sp["s28"] if sp.get("s28") else (sp.get("p") or 0)


def xu_huong(tr):
    """'tăng' / 'giảm' / None: 3 ngày cuối so 3 ngày đầu trong 7 ngày, ngưỡng ±30%."""
    if not tr or len(tr) < 6:
        return None
    dau, cuoi = sum(tr[:3]), sum(tr[-3:])
    if dau == 0:
        return "tăng" if cuoi > 0 else None
    r = cuoi / dau - 1
    return "tăng" if r >= 0.3 else "giảm" if r <= -0.3 else None


def _khung(gia, khung_gia):
    for i, k in enumerate(khung_gia):
        if k["den"] is None or gia < k["den"]:
            return i
    return len(khung_gia) - 1


def _top_shop(ds, n=3):
    theo = defaultdict(float)
    for sp in ds:
        theo[sp.get("sh") or "(chưa rõ tên)"] += sp.get("a28") or 0
    return sorted(theo.items(), key=lambda x: -x[1])[:n]


def _ngay_len_san(lt):
    if not lt:
        return None
    if isinstance(lt, (int, float)):
        try:
            return datetime.utcfromtimestamp(lt if lt < 1e11 else lt / 1000).date()
        except (OverflowError, OSError, ValueError):
            return None
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)", str(lt))
    return date(int(m[1]), int(m[2]), int(m[3])) if m else None


def _giong(a, b):
    """Độ giống tên (Jaccard trên từ, bỏ dấu)."""
    x, y = set(N(a).split()), set(N(b).split())
    return len(x & y) / len(x | y) if x and y else 0


def tinh(ds, luot, ch, truoc=None):
    """ds: SP đã làm sạch (lam_sach). truoc: ds của lượt quét trước (tuỳ chọn)."""
    kg = ch["khung_gia"]
    ten_nhom = {g["ma"]: g["ten"] for g in ch["nhom"]}
    mau_nhom = {g["ma"]: g["mau"] for g in ch["nhom"]}
    tt = luot.get("thong_tin", {})
    ngay_chot = None
    if m := re.match(r"(\d\d)/(\d\d)/(\d{4})", tt.get("ngay_chot", "")):
        ngay_chot = date(int(m[3]), int(m[2]), int(m[1]))

    # ---- từng SP
    theo_nhom = defaultdict(list)
    for sp in ds:
        sp["gia"] = gia_tb(sp)
        sp["nhip"] = (sp.get("s7") or 0) * 4 / sp["s28"] if sp.get("s28") else None
        sp["xh"] = xu_huong(sp.get("tr"))
        sp["ngay_ls"] = _ngay_len_san(sp.get("lt"))
        theo_nhom[sp["nhom"]].append(sp)
    for g, lst in theo_nhom.items():
        lst.sort(key=lambda s: (-(s.get("s28") or 0), -(s.get("a28") or 0)))
        for i, sp in enumerate(lst, 1):
            sp["hang"] = i

    # ---- KPI chung
    kpi = {
        "sp": len(ds), "shop": len({sp.get("sh") for sp in ds}),
        "don28": sum(sp.get("s28") or 0 for sp in ds), "dt28": sum(sp.get("a28") or 0 for sp in ds),
        "don7": sum(sp.get("s7") or 0 for sp in ds),
        "video_fm": sum(sp.get("v") or 0 for sp in ds),
        "video_tim": sum(sp["vid_n"] for sp in ds), "xem": sum(sp["vid_xem"] for sp in ds),
        "sp_co_video": sum(1 for sp in ds if sp["vid_n"]),
    }

    # ---- nhóm
    nhom = []
    for g in ch["nhom"]:
        lst = theo_nhom.get(g["ma"], [])
        if not lst:
            continue
        dt = sum(s.get("a28") or 0 for s in lst)
        don = sum(s.get("s28") or 0 for s in lst)
        dai = [0.0] * len(kg)
        for s in lst:
            dai[_khung(s["gia"], kg)] += s.get("s28") or 0
        dai = [x / don if don else 0 for x in dai]
        chinh = max(range(len(kg)), key=lambda i: dai[i])
        top = _top_shop(lst)
        nhom.append({
            "ma": g["ma"], "ten": g["ten"], "mau": g["mau"], "sp": len(lst),
            "shop": len({s.get("sh") for s in lst}), "don28": don, "dt28": dt,
            "don7": sum(s.get("s7") or 0 for s in lst),
            "nhip": sum(s.get("s7") or 0 for s in lst) * 4 / don if don else None,
            "top3": sum(v for _, v in top) / dt if dt else None,
            "khung": dai, "khung_chinh": f"{kg[chinh]['ten']} ({dai[chinh] * 100:.0f}%)", "shop_lon": top,
        })

    # ---- ngách (cho ma trận)
    theo_ngach = defaultdict(list)
    for sp in ds:
        theo_ngach[sp["ngach"]].append(sp)
    ngach = []
    for ten, lst in theo_ngach.items():
        dt = sum(s.get("a28") or 0 for s in lst)
        luy_ke = sum(s.get("s") or 0 for s in lst)
        vfm = sum(s.get("v") or 0 for s in lst)
        g_theo = defaultdict(float)
        for s in lst:
            g_theo[s["nhom"]] += s.get("a28") or 0
        g = max(g_theo, key=g_theo.get)
        top = _top_shop(lst)
        ngach.append({
            "ten": ten, "nhom": g, "mau": mau_nhom.get(g, 1), "sp": len(lst),
            "don28": sum(s.get("s28") or 0 for s in lst), "dt28": dt,
            "top3": sum(v for _, v in top) / dt if dt else None, "video_fm": vfm,
            "video_1000": vfm / luy_ke * 1000 if luy_ke else None,
            "video_tim": sum(s["vid_n"] for s in lst), "shop_lon": [t for t, _ in top],
        })
    ngach.sort(key=lambda x: -x["dt28"])
    toi_thieu = ch["bang"]["ngach_toi_thieu_sp"]
    ma_tran = [x for x in ngach if x["sp"] >= toi_thieu and x["top3"] is not None and x["video_1000"]]

    # ---- shop
    theo_shop = defaultdict(list)
    for sp in ds:
        theo_shop[sp.get("sh") or "(chưa rõ tên)"].append(sp)
    shop = []
    for ten, lst in theo_shop.items():
        g_theo = defaultdict(float)
        for s in lst:
            g_theo[s["nhom"]] += s.get("a28") or 0
        shop.append({
            "ten": ten, "nhom": max(g_theo, key=g_theo.get), "sp": len(lst),
            "don28": sum(s.get("s28") or 0 for s in lst), "dt28": sum(s.get("a28") or 0 for s in lst),
            "don7": sum(s.get("s7") or 0 for s in lst), "video_fm": sum(s.get("v") or 0 for s in lst),
            "sp_dau": max(lst, key=lambda s: s.get("s28") or 0), "nha": lst[0]["nha"],
        })
    shop.sort(key=lambda x: -x["dt28"])

    # ---- thương hiệu nhà
    nha_ds = [sp for sp in ds if sp["nha"] == "xac_nhan"]
    nha_ds.sort(key=lambda s: ([g["ma"] for g in ch["nhom"]].index(s["nhom"]), s["hang"]))
    nha_shop = []
    for ten in dict.fromkeys(sp["sh"] for sp in nha_ds):
        lst = [s for s in nha_ds if s["sh"] == ten]
        nha_shop.append({"ten": ten, "listing": len(lst), "don28": sum(s.get("s28") or 0 for s in lst),
                         "dt28": sum(s.get("a28") or 0 for s in lst), "don7": sum(s.get("s7") or 0 for s in lst)})
    nha_shop.sort(key=lambda x: -x["don28"])
    van_de = []
    for i, a in enumerate(nha_ds):
        for b in nha_ds[i + 1:]:
            if a["sh"] != b["sh"] and a["ngach"] == b["ngach"] and _giong(a["t"], b["t"]) >= 0.5:
                van_de.append({"loai": "trung", "a": a, "b": b})
    for sp in nha_ds:
        if not sp.get("s28"):
            van_de.append({"loai": "khong_don", "a": sp})
    for s in shop:
        if s["nha"] == "nghi":
            van_de.append({"loai": "nghi", "shop": s})

    # ---- video & KOC toàn bài
    tat_ca_video = {}
    koc = {}
    for sp in ds:
        for v in sp["vid_top"]:
            tat_ca_video.setdefault(v[0], (v, sp))
        for k in sp["koc_top"]:
            o = koc.setdefault(k[0], {"u": k[0], "xem": 0, "fo": 0, "video": 0, "sp": 0, "nhom": defaultdict(float)})
            o["xem"] += k[1]
            o["fo"] = max(o["fo"], k[2])
            o["video"] += k[3]
            o["sp"] += 1
            o["nhom"][sp["nhom"]] += k[1]
    top_video = sorted(tat_ca_video.values(), key=lambda x: -(x[0][2] or 0))[:ch["bang"]["top_video"]]
    top_koc = sorted(koc.values(), key=lambda x: -x["xem"])[:ch["bang"]["top_koc"]]
    for o in top_koc:
        o["nhom"] = max(o["nhom"], key=o["nhom"].get)

    # ---- tín hiệu nhanh
    tang_toc = sorted([s for s in ds if (s.get("s28") or 0) >= 100 and (s["nhip"] or 0) >= 1.5], key=lambda s: -(s.get("s7") or 0))[:10]
    giam_toc = sorted([s for s in ds if (s.get("s28") or 0) >= 300 and s["nhip"] is not None and s["nhip"] <= 0.6], key=lambda s: -(s.get("s28") or 0))[:10]
    moi = []
    if ngay_chot:
        moi = sorted([s for s in ds if s["ngay_ls"] and (ngay_chot - s["ngay_ls"]).days <= 75 and (s.get("s28") or 0) >= 300],
                     key=lambda s: -(s.get("s28") or 0))[:10]

    # ---- so với lượt trước
    so_sanh = None
    if truoc:
        cu = {s["id"]: s for s in truoc}
        cu_nhom = defaultdict(lambda: [0, 0])
        for s in truoc:
            cu_nhom[s["nhom"]][0] += s.get("s28") or 0
            cu_nhom[s["nhom"]][1] += s.get("a28") or 0
        cu_hang = {}
        for g in {s["nhom"] for s in truoc}:
            for i, s in enumerate(sorted([x for x in truoc if x["nhom"] == g], key=lambda x: -(x.get("s28") or 0)), 1):
                cu_hang[s["id"]] = i
        n_top = ch["bang"]["chi_tiet_moi_nhom"]
        so_sanh = {
            "ngay_truoc": (truoc[0].get("_ngay_chot") if truoc else None),
            "kpi_truoc": {"sp": len(truoc), "don28": sum(s.get("s28") or 0 for s in truoc), "dt28": sum(s.get("a28") or 0 for s in truoc)},
            "nhom": {g: {"don28": v[0], "dt28": v[1]} for g, v in cu_nhom.items()},
            "vao_top": [s for s in ds if s["hang"] <= n_top and cu_hang.get(s["id"], 999) > n_top],
            "roi_top": [cu[i] for i, h in cu_hang.items() if h <= n_top and not any(s["id"] == i and s["hang"] <= n_top for s in ds)],
            "thay_doi": {s["id"]: {"don28": cu[s["id"]].get("s28") or 0, "hang": cu_hang.get(s["id"])} for s in ds if s["id"] in cu},
        }

    return {
        "kpi": kpi, "nhom": nhom, "ten_nhom": ten_nhom, "mau_nhom": mau_nhom, "theo_nhom": theo_nhom,
        "ngach": ngach, "ma_tran": ma_tran, "shop": shop, "nha": nha_ds, "nha_shop": nha_shop, "van_de_nha": van_de,
        "top_video": top_video, "top_koc": top_koc, "tang_toc": tang_toc, "giam_toc": giam_toc, "moi_len_san": moi,
        "so_sanh": so_sanh, "ngay_chot": ngay_chot,
    }


def _r(x, n=1):
    return round(x, n) if isinstance(x, float) else x


def tom_tat(M, luot, ch):
    """Bản tóm tắt gọn (vài KB) để Claude đọc và viết nhận định — không cần đọc cả trang."""
    ss = M["so_sanh"]

    def sp_gon(s, day_du=True):
        d = {"ten": s["t"][:55], "shop": s.get("sh"), "gia": round(s["gia"]), "don28": s.get("s28"),
             "don7": s.get("s7"), "nhip7": _r(s["nhip"], 2)}
        if day_du:
            d.update({"ngach": s["ngach"], "xh": s["xh"], "video_fm": s.get("v"), "xem": s["vid_xem"]})
            if s["koc_top"]:
                d["koc"] = [k[0] for k in s["koc_top"][:2]]
            if s["ngay_ls"]:
                d["len_san"] = s["ngay_ls"].strftime("%d/%m/%y")
        else:
            d["nhom"] = M["ten_nhom"].get(s["nhom"])
        if ss and s["id"] in ss["thay_doi"]:
            d["don28_truoc"] = ss["thay_doi"][s["id"]]["don28"]
            d["hang_truoc"] = ss["thay_doi"][s["id"]]["hang"]
        return d

    tt = luot.get("thong_tin", {})
    kq = {
        "nganh": ch["tieu_de_trang"], "ngay_quet": tt.get("ngay_quet"), "ngay_chot": tt.get("ngay_chot"),
        "kpi": M["kpi"],
        "nhom": [{"ma": g["ma"], "ten": g["ten"], "sp": g["sp"], "shop": g["shop"], "don28": g["don28"], "dt28": round(g["dt28"]),
                  "don7": g["don7"], "nhip7": _r(g["nhip"], 2), "top3_shop": _r(g["top3"], 2), "khung_gia_chinh": g["khung_chinh"],
                  "shop_lon": [[t, round(v)] for t, v in g["shop_lon"]]} for g in M["nhom"]],
        "ngach": [{"ten": x["ten"], "nhom": M["ten_nhom"].get(x["nhom"]), "sp": x["sp"], "don28": x["don28"], "dt28": round(x["dt28"]),
                   "top3_shop": _r(x["top3"], 2), "video_1000_don": _r(x["video_1000"], 0)} for x in M["ngach"]],
        "top5_moi_nhom": {g["ten"]: [sp_gon(s) for s in M["theo_nhom"][g["ma"]][:5]] for g in M["nhom"]},
        "tang_toc": [sp_gon(s, False) for s in M["tang_toc"][:6]],
        "giam_toc": [sp_gon(s, False) for s in M["giam_toc"][:6]],
        "moi_len_san_ban_tot": [dict(sp_gon(s, False), len_san=s["ngay_ls"].strftime("%d/%m/%y")) for s in M["moi_len_san"][:6]],
        "thuong_hieu_nha": {
            "shop": M["nha_shop"],
            "listing": [dict(sp_gon(s, False), hang=f'{s["hang"]}/{len(M["theo_nhom"][s["nhom"]])}', video_fm=s.get("v"),
                             dan_dau=None if s["hang"] == 1 else {"shop": M["theo_nhom"][s["nhom"]][0].get("sh"),
                                                                    "don28": M["theo_nhom"][s["nhom"]][0].get("s28"),
                                                                    "gia": round(M["theo_nhom"][s["nhom"]][0]["gia"])})
                        for s in M["nha"]],
            "van_de": [{"loai": v["loai"], "chi_tiet": (f"{v['a']['sh']} và {v['b']['sh']}: {v['a']['t'][:50]}" if v["loai"] == "trung"
                                                         else v["a"]["t"][:60] + " · " + v["a"]["sh"] if v["loai"] == "khong_don"
                                                         else v["shop"]["ten"])} for v in M["van_de_nha"]],
        },
        "tu_khoa_chua_dap_ung": [k for k in luot.get("tu_khoa", []) if not k.get("tren_ke")],
        "top_koc": [{"u": k["u"], "xem": k["xem"], "fo": k["fo"], "sp": k["sp"], "nhom": M["ten_nhom"].get(k["nhom"])} for k in M["top_koc"][:10]],
    }
    if ss:
        kq["so_voi_lan_truoc"] = {
            "kpi_truoc": ss["kpi_truoc"],
            "nhom_truoc": {M["ten_nhom"].get(g, g): v for g, v in ss["nhom"].items()},
            "vao_top10": [dict(sp_gon(s, False), hang=s["hang"]) for s in ss["vao_top"]],
            "roi_top10": [{"ten": s["t"][:70], "shop": s.get("sh"), "don28_truoc": s.get("s28")} for s in ss["roi_top"]],
        }
    return kq


def co_so(x):
    return x is not None and not (isinstance(x, float) and math.isnan(x))
