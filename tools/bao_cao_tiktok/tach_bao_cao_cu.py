"""Tách số liệu từ một trang báo cáo "Thị trường ... TikTok" đã đăng (HTML) về dạng dữ liệu đầu vào.

Dùng khi chỉ còn trang báo cáo mà mất dữ liệu gốc: để so sánh lần quét mới với lần trước,
hoặc để dựng lại báo cáo cũ bằng bộ dựng mới.

  python3 -m tools.bao_cao_tiktok.tach_bao_cao_cu bao_cao_cu.html du_lieu/tranh_lich/2026-09-26

Giới hạn: tên SP trong bảng đã bị cắt ~95 ký tự; đơn từng ngày (trend) được ước lại từ hình
sparkline nên chỉ đúng hình dạng; không có hạng mục, mã shop, từ khoá tìm.
"""
import html
import json
import re
import sys
from pathlib import Path

_TD = re.compile(r"<td([^>]*)>(.*?)</td>", re.S)
_TAG = re.compile(r"<[^>]+>")


def _text(s):
    return html.unescape(_TAG.sub("", s)).strip()


def _dv(attrs):
    m = re.search(r'data-v="([^"]*)"', attrs)
    return m.group(1) if m else None


def _num(v):
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return None


def _pane(s, pid):
    """Nội dung một tab (div/main id=pid class=pane) — tới tab kế tiếp."""
    m = re.search(r'<(?:main|div) id="%s" class="pane"' % re.escape(pid), s)
    if not m:
        return ""
    n = re.search(r'<(?:main|div) id="[\w-]+" class="pane"', s[m.end():])
    return s[m.start(): m.end() + n.start()] if n else s[m.start():]


def _markdown(inner):
    """<a href=u>t</a> -> [t](u), bỏ thẻ khác."""
    inner = re.sub(r'<a href="([^"]+)"[^>]*>(.*?)</a>', lambda m: "[%s](%s)" % (_text(m.group(2)), m.group(1)), inner, flags=re.S)
    return _text(inner)


def _trend(points, s7):
    """Ước đơn từng ngày từ toạ độ y của sparkline (y=2 cao nhất, y=16 thấp nhất)."""
    ys = [float(p.split(",")[1]) for p in points.split()]
    w = [(16 - y) + 1.4 for y in ys]  # giả định ngày thấp nhất ~10% biên độ
    tong = sum(w) or 1
    kq = [round(x / tong * (s7 or 0)) for x in w]
    if kq:
        kq[-1] += (s7 or 0) - sum(kq)
    return kq


def tach(duong_dan):
    s = open(duong_dan, encoding="utf-8").read()
    ket_qua = {"fastmoss": {}, "video": {"sp": {}}, "tu_khoa": [], "nhan_dinh": {}, "thong_tin": {}}

    # ---- nhóm: key -> tên (từ select lọc)
    nhom = dict(re.findall(r'<option value="(\w+)">([^<]+)</option>', _pane(s, "all")))
    nhom = {k: html.unescape(v) for k, v in nhom.items()}

    # ---- bảng toàn bộ sản phẩm
    tb = _pane(s, "all")
    for m in re.finditer(r'<tr( class="home")? data-q="[^"]*" data-g="(\w+)">(.*?)</tr>', tb, re.S):
        tds = _TD.findall(m.group(3))
        if len(tds) < 15:
            continue
        a = re.search(r'pdp/(\d+)"[^>]*>(.*?)</a>', tds[1][1], re.S)
        pid, ten = a.group(1), _text(a.group(2))
        ngach = _text(re.sub(r".*<br>", "", tds[3][1], flags=re.S))
        s28, a28, s7 = _num(_dv(tds[5][0])), _num(_dv(tds[6][0])), _num(_dv(tds[7][0]))
        pts = re.search(r'points="([^"]+)"', tds[8][1])
        lt = _dv(tds[14][0])
        ket_qua["fastmoss"][pid] = {
            "t": ten, "sh": _text(tds[2][1]), "sid": "", "c": "",
            "p": _num(_dv(tds[4][0])), "s": _num(_dv(tds[9][0])), "v": _num(_dv(tds[10][0])), "a": None,
            "s7": s7, "s28": s28, "a28": a28, "a7": None,
            "tr": _trend(pts.group(1), s7) if pts else [],
            "lt": f"{lt[:4]}-{lt[4:6]}-{lt[6:]}" if lt and len(lt) == 8 else None,
            "k": [], "_g": m.group(2), "_n": ngach, "_tai_dung": True,
        }
        ket_qua["video"]["sp"][pid] = {
            "n": _num(_dv(tds[11][0])) or 0, "xem": _num(_dv(tds[12][0])) or 0,
            "koc": _num(_dv(tds[13][0])) or 0, "v": [], "k": [],
        }

    # ---- KOC theo FastMoss (chỉ có ở bảng thương hiệu nhà)
    for m in re.finditer(r"<tr class=\"home\">(.*?)</tr>", _pane(s, "nha"), re.S):
        tds = _TD.findall(m.group(1))
        a = re.search(r"pdp/(\d+)", m.group(1))
        if a and a.group(1) in ket_qua["fastmoss"] and len(tds) >= 10:
            ket_qua["fastmoss"][a.group(1)]["a"] = _num(_dv(tds[9][0]))

    # ---- chi tiết top video / KOC (details dựng sẵn)
    for m in re.finditer(r'<details class="it" id="d-(\d+)".*?</details>', s, re.S):
        pid, seg = m.group(1), m.group(0)
        sp = ket_qua["video"]["sp"].setdefault(pid, {"n": 0, "xem": 0, "koc": 0, "v": [], "k": []})
        for v in re.finditer(r'@([^/"]+)/video/(\d+)"[^>]*>(.*?)</a> <span class="muted">· @[^·]+· ([\d.]+) lượt xem · ([\d/]+)', seg, re.S):
            sp["v"].append([v.group(2), v.group(1), int(v.group(4).replace(".", "")), v.group(5), _text(v.group(3))])
        for k in re.finditer(r'tiktok\.com/@([^"/]+)"[^>]*>@[^<]+</a> <span class="muted">· ([\d.]+) lượt xem · ([\d.]+) follower · (\d+) video', seg):
            sp["k"].append([k.group(1), int(k.group(2).replace(".", "")), int(k.group(3).replace(".", "")), int(k.group(4))])

    # ---- từ khoá Seller Center (bảng trong tab tổng quan)
    tq = _pane(s, "tq")
    i = tq.find("Từ khoá khách đang tìm")
    if i >= 0:
        bang = tq[i: tq.find("</table>", i)]
        for m in re.finditer(r"<tr>(<td.*?)</tr>", bang, re.S):
            tds = _TD.findall(m.group(1))
            if len(tds) == 5:
                ket_qua["tu_khoa"].append({"tu": _text(tds[0][1]), "luot": _text(tds[1][1]), "hang_muc": _text(tds[2][1]),
                                           "tren_ke": _num(_dv(tds[3][0])), "tin_hieu": _text(tds[4][1])})

    # ---- nhận định (Ba điều rút ra + Việc nên làm)
    kl = re.search(r'<div class="concl">(.*?)</div></section>', tq, re.S)
    if kl:
        ket_qua["nhan_dinh"]["ket_luan"] = [
            {"tieu_de": _text(t), "noi_dung": _markdown(p)}
            for t, p in re.findall(r"<div><h3>(.*?)</h3><p>(.*?)</p></div>", kl.group(1), re.S)]
    viec = []
    for c in re.finditer(r'<article class="card"><span class="eyebrow">(.*?)</span><h3>(.*?)</h3><dl>(.*?)</dl></article>', tq, re.S):
        dd = dict((_text(k), _markdown(v)) for k, v in re.findall(r"<dt>(.*?)</dt><dd>(.*?)</dd>", c.group(3), re.S))
        viec.append({"nhan": _text(c.group(1)), "tieu_de": _text(c.group(2)),
                     "vi_sao": dd.get("Vì sao", ""), "lam_gi": dd.get("Làm gì", ""), "danh_doi": dd.get("Đánh đổi", "")})
    if viec:
        ket_qua["nhan_dinh"]["viec_nen_lam"] = viec

    # ---- thông tin lượt quét (tab Cách lấy số)
    cach = _text(_pane(s, "cach"))
    tt = ket_qua["thong_tin"]
    if (m := re.search(r"Ngày quét: (\d\d/\d\d/\d{4})", cach)):
        tt["ngay_quet"] = m.group(1)
    if (m := re.search(r"tính tới hết (\d\d/\d\d/\d{4})", cach)):
        tt["ngay_chot"] = m.group(1)
    if (m := re.search(r"khoảng (\d+) lượt tìm với (\d+) từ khoá", cach)):
        tt["luot_tim_fastmoss"], tt["tu_khoa_fastmoss"] = int(m.group(1)), int(m.group(2))
    if (m := re.search(r"với (\d+) từ khoá[,;]", cach)):
        tt["tu_khoa_video"] = int(m.group(1))
    if (m := re.search(r"tổng ([\d.]+) video", cach)):
        tt["tong_video"] = int(m.group(1).replace(".", ""))
    if (m := re.search(r"Lọc: ([\d.]+) SP", cach)):
        tt["sp_truoc_loc"] = int(m.group(1).replace(".", ""))
    if (m := re.search(r"<title>(.*?)</title>", s)):
        tt["tieu_de_trang"] = html.unescape(m.group(1))
    tt["nhom_trong_bao_cao"] = nhom
    tt["nguon"] = f"Tách từ báo cáo HTML {Path(duong_dan).name}"
    return ket_qua


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 2:
        print(__doc__)
        return 1
    kq = tach(argv[0])
    thu_muc = Path(argv[1])
    thu_muc.mkdir(parents=True, exist_ok=True)
    for ten, du_lieu in kq.items():
        if du_lieu:
            (thu_muc / f"{ten}.json").write_text(json.dumps(du_lieu, ensure_ascii=False, indent=1), encoding="utf-8")
    co_video = sum(1 for v in kq["video"]["sp"].values() if v["v"])
    print(f"Đã tách {len(kq['fastmoss'])} SP, chi tiết video cho {co_video} SP, "
          f"{len(kq['tu_khoa'])} từ khoá, {len(kq['nhan_dinh'].get('viec_nen_lam', []))} việc nên làm -> {thu_muc}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
