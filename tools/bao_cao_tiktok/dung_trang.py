"""Dựng trang HTML báo cáo từ các chỉ số (giữ đúng mẫu "Thị trường ... TikTok")."""
import html
import math
import re
from pathlib import Path

from tools.bao_cao_tiktok.lam_sach import N

_THU_MUC = Path(__file__).parent


# ---------------- định dạng số kiểu Việt ----------------
def so(n):
    if n is None:
        return "—"
    return f"{round(n):,}".replace(",", ".")


def gon(n):
    """9.441.599.821 -> '9,44 tỷ'; 812.862.076 -> '812,9 tr'; 32.454 -> '32k'."""
    if n is None:
        return "—"
    n = float(n)
    if abs(n) >= 1e9:
        return f"{n / 1e9:.2f}".replace(".", ",") + " tỷ"
    if abs(n) >= 1e6:
        return f"{n / 1e6:.1f}".replace(".", ",") + " tr"
    if abs(n) >= 1e4:
        return f"{n / 1e3:.0f}k"
    return so(n)


def pct(x, d=0):
    return "—" if x is None else f"{x * 100:.{d}f}".replace(".", ",") + "%"


def e(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def md(s):
    """Văn bản nhận định: [chữ](link) -> thẻ a; còn lại escape."""
    out, i = [], 0
    for m in re.finditer(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", s or ""):
        out.append(e(s[i:m.start()]))
        out.append(f'<a href="{e(m.group(2))}" target="_blank" rel="noopener">{e(m.group(1))}</a>')
        i = m.end()
    out.append(e((s or "")[i:]))
    return "".join(out)


def link_sp(sp, n=95):
    return f'<a href="https://shop.tiktok.com/vn/pdp/{e(sp["id"])}" target="_blank" rel="noopener">{e(sp["t"][:n])}</a>'


def td_n(v, hien=None, cls="n"):
    dv = "" if v is None else f' data-v="{v:.3f}"' if isinstance(v, float) and not float(v).is_integer() else f' data-v="{int(v)}"'
    return f'<td class="{cls}"{dv}>{hien if hien is not None else so(v)}</td>'


def sparkline(tr):
    if not tr or len(tr) < 2:
        return "—"
    lo, hi = min(tr), max(tr)
    pts = []
    for i, v in enumerate(tr):
        x = 2 + i * 60 / (len(tr) - 1)
        y = 9.0 if hi == lo else 16 - (v - lo) / (hi - lo) * 14
        pts.append(f"{x:.1f},{y:.1f}")
    cx, cy = pts[-1].split(",")
    return (f'<svg class="sp" viewBox="0 0 64 18" width="64" height="18" aria-hidden="true">'
            f'<polyline points="{" ".join(pts)}"/><circle cx="{cx}" cy="{cy}" r="2"/></svg>')


def td_xu_huong(sp):
    tr = sp.get("tr") or []
    dau, cuoi = sum(tr[:3]), sum(tr[-3:])
    dv = round((cuoi / dau - 1) * 100) if dau else 0
    chip = {"tăng": ' <span class="chip up">tăng</span>', "giảm": ' <span class="chip dn">giảm</span>'}.get(sp["xh"], "")
    return f'<td data-v="{dv}">{sparkline(tr)}{chip}</td>'


def ngay_ngan(d):
    return d.strftime("%d/%m/%y") if d else "—"


# ---------------- các phần trang ----------------
class Trang:
    def __init__(self, M, luot, ch, tab_giu=None):
        self.M, self.luot, self.ch = M, luot, ch
        self.tt = luot.get("thong_tin", {})
        self.nd = luot.get("nhan_dinh", {}) or {}
        self.tab_giu = tab_giu or []  # [(id, nhãn, html)]

    def dot(self, nhom):
        return f'<span class="dot g{self.M["mau_nhom"].get(nhom, 1)}"></span>'

    def chip_nha(self, sp):
        return f' <span class="chip home">{e(sp["sh"])}</span>' if sp["nha"] == "xac_nhan" else ""

    # ---- Tổng quan
    def tong_quan(self):
        M, k = self.M, self.M["kpi"]
        kpi = [(so(k["sp"]), "sản phẩm có bán trong 28 ngày"), (so(k["shop"]), "shop"),
               (so(k["don28"]), "đơn trong 28 ngày"), (gon(k["dt28"]), "doanh thu 28 ngày (ước tính)"),
               (so(k["video_fm"]), "video gắn SP (FastMoss)")]
        if self.luot.get("co_video"):
            kpi.append((so(k["video_tim"]), f"video tìm được · {gon(k['xem'])} lượt xem"))
        ss = M["so_sanh"]
        if ss:
            kt = ss["kpi_truoc"]
            kpi[2] = (so(k["don28"]), f"đơn trong 28 ngày · lần trước {so(kt['don28'])}")
            kpi[3] = (gon(k["dt28"]), f"doanh thu 28 ngày (ước tính) · lần trước {gon(kt['dt28'])}")
        h = ['<main id="tq" class="pane" role="tabpanel"><section><div class="kpis">']
        h += [f'<div class="kpi"><b>{a}</b><span>{e(b)}</span></div>' for a, b in kpi]
        h.append("</div></section>")

        kl = self.nd.get("ket_luan") or []
        if kl:
            h.append(f'<section><h2>{e(self.nd.get("tieu_de_ket_luan") or "Ba điều rút ra")}</h2><div class="concl">')
            h += [f'<div><h3>{e(x["tieu_de"])}</h3><p>{md(x["noi_dung"])}</p></div>' for x in kl]
            h.append("</div></section>")
        else:
            h.append('<section><h2>Điều rút ra</h2><p class="note">Chưa có nhận định cho lượt quét này. '
                     'Nhờ Claude đọc file <code>tom_tat.json</code> và viết <code>nhan_dinh.json</code>, rồi dựng lại trang.</p></section>')

        n = len(M["nhom"])
        ten_so = {1: "Một", 2: "Hai", 3: "Ba", 4: "Bốn", 5: "Năm", 6: "Sáu", 7: "Bảy", 8: "Tám"}.get(n, str(n))
        h.append(f'<section><h2>{ten_so} nhóm hàng</h2><p class="note">Số đơn và doanh thu là của 28 ngày gần nhất '
                 f'(tới {e(self.tt.get("ngay_chot", ""))}) theo ước tính FastMoss. Bấm tiêu đề cột để sắp xếp.</p>'
                 '<div class="tw"><table class="x"><thead><tr><th class="s">Nhóm</th><th class="s n">SP</th><th class="s n">Shop</th>'
                 '<th class="s n b">Bán 28 ngày</th><th class="s n b">Doanh thu 28 ngày</th><th class="s n">Bán 7 ngày</th>'
                 '<th class="s n" title="Bán 7 ngày × 4 so với 28 ngày. Trên 100% là đang tăng tốc">Nhịp 7 ngày</th>'
                 + ('<th class="s n" title="Đơn 28 ngày so với lần quét trước">So lần trước</th>' if ss else "")
                 + '<th class="s n">Top 3 shop nắm</th><th>Khung giá chính</th><th>3 shop lớn nhất</th></tr></thead><tbody>')
        for g in M["nhom"]:
            doi = ""
            if ss:
                cu = ss["nhom"].get(g["ma"], {}).get("don28")
                r = g["don28"] / cu - 1 if cu else None
                doi = td_n(r, ("+" if r and r > 0 else "") + pct(r) if r is not None else "mới")
            shop = "<br>".join(f'{e(t)} <span class=muted>{gon(v)}</span>' for t, v in g["shop_lon"])
            h.append(f'<tr><td>{self.dot(g["ma"])}{e(g["ten"])}</td>{td_n(g["sp"])}{td_n(g["shop"])}{td_n(g["don28"])}'
                     f'{td_n(g["dt28"], gon(g["dt28"]))}{td_n(g["don7"])}{td_n(g["nhip"], pct(g["nhip"]))}{doi}'
                     f'{td_n(g["top3"], pct(g["top3"]))}<td>{e(g["khung_chinh"])}</td><td>{shop}</td></tr>')
        h.append("</tbody></table></div></section>")
        if ss:
            h.append(self.so_sanh())

        kg = self.ch["khung_gia"]
        mau_khung = ["g4", "g3", "g2", "g1", "g5"]
        h.append('<section><h2>Khung giá theo số đơn 28 ngày</h2><p class="note">Giá tính bằng doanh thu 28 ngày chia số đơn, '
                 'tức giá khách thực trả trung bình, không phải giá niêm yết.</p><div class="legend">')
        h += [f'<span><i style="background:var(--{mau_khung[i][0]}{mau_khung[i][1:]})"></i>{e(k["ten"])}</span>' for i, k in enumerate(kg)]
        h.append('</div><div class="bands" style="margin-top:10px">')
        for g in M["nhom"]:
            tip = " · ".join(f'{k["ten"]}: {g["khung"][i] * 100:.0f}%' for i, k in enumerate(kg))
            seg = "".join(f'<i style="width:{g["khung"][i] * 100:.1f}%;background:var(--{mau_khung[i]})"></i>' for i in range(len(kg)))
            h.append(f'<div class="band"><span>{self.dot(g["ma"])}{e(g["ten"])}</span><div class="row" title="{e(tip)}">{seg}</div></div>')
        h.append("</div></section>")

        tk = self.luot.get("tu_khoa") or []
        if tk:
            h.append('<section><h2>Từ khoá khách đang tìm</h2><p class="note">Từ Seller Center, mục Cơ hội sản phẩm, tab Từ khoá thịnh hành. '
                     '"SP trên kệ" là số SP gắn đúng từ khoá; bằng 0 nghĩa là khách tìm mà gần như không ai đáp ứng.</p>'
                     '<div class="tw"><table class="x"><thead><tr><th class="s">Từ khoá</th><th class="s">Lượt tìm</th><th class="s">Hạng mục</th>'
                     '<th class="s n">SP trên kệ</th><th class="s">Tín hiệu</th></tr></thead><tbody>')
            for x in tk:
                tin = f'<span class="chip up">{e(x.get("tin_hieu"))}</span>' if not x.get("tren_ke") else e(x.get("tin_hieu"))
                h.append(f'<tr><td>{e(x.get("tu"))}</td><td>{e(x.get("luot"))}</td><td class="muted">{e(x.get("hang_muc"))}</td>'
                         f'{td_n(x.get("tren_ke"))}<td>{tin}</td></tr>')
            h.append("</tbody></table></div></section>")

        viec = self.nd.get("viec_nen_lam") or []
        if viec:
            h.append('<section><h2>Việc nên làm</h2><div class="cards">')
            for v in viec:
                h.append(f'<article class="card"><span class="eyebrow">{e(v.get("nhan"))}</span><h3>{e(v.get("tieu_de"))}</h3><dl>'
                         f'<dt>Vì sao</dt><dd>{md(v.get("vi_sao"))}</dd><dt>Làm gì</dt><dd>{md(v.get("lam_gi"))}</dd>'
                         f'<dt>Đánh đổi</dt><dd>{md(v.get("danh_doi"))}</dd></dl></article>')
            h.append("</div></section>")
        h.append("</main>")
        return "".join(h)

    def so_sanh(self):
        ss = self.M["so_sanh"]
        h = [f'<section><h2>So với lần quét trước</h2><p class="note">Lần trước chốt số ngày {e(ss.get("ngay_truoc") or "?")}. '
             'Hạng là thứ hạng trong nhóm theo đơn 28 ngày.</p><div class="dgrid"><div><h3>Mới vào top 10</h3>']
        if ss["vao_top"]:
            h.append('<ul class="why">')
            for sp in ss["vao_top"]:
                cu = ss["thay_doi"].get(sp["id"])
                h.append(f'<li>{self.dot(sp["nhom"])}{link_sp(sp, 60)} <span class="muted">· {e(sp.get("sh"))} · hạng {sp["hang"]}'
                         f'{" (trước " + str(cu["hang"]) + ")" if cu and cu["hang"] else " (mới)"} · {so(sp.get("s28"))} đơn</span></li>')
            h.append("</ul>")
        else:
            h.append('<p class="muted">Không có.</p>')
        h.append("</div><div><h3>Rời top 10</h3>")
        if ss["roi_top"]:
            h.append('<ul class="why">')
            h += [f'<li>{self.dot(sp["nhom"])}{link_sp(sp, 60)} <span class="muted">· {e(sp.get("sh"))} · lần trước {so(sp.get("s28"))} đơn</span></li>'
                  for sp in ss["roi_top"]]
            h.append("</ul>")
        else:
            h.append('<p class="muted">Không có.</p>')
        h.append("</div></div></section>")
        return "".join(h)

    # ---- Ma trận
    def ma_tran(self):
        mt = self.M["ma_tran"]
        if len(mt) < 2:
            return '<p class="note">Chưa đủ ngách (mỗi ngách cần ít nhất 3 SP) để vẽ ma trận.</p>'
        W, H, X0, X1, Y0, Y1 = 760, 460, 64, 712, 24, 404
        xs = [x["top3"] for x in mt]
        ys = [x["video_1000"] for x in mt]
        xlo = min(0.9, math.floor(min(xs) * 10) / 10)
        ylo = 10 ** math.floor(math.log10(min(ys)))
        yhi = 10 ** math.ceil(math.log10(max(ys)))
        if yhi <= ylo:
            yhi = ylo * 10
        fx = lambda v: X0 + (v - xlo) / (1 - xlo) * (X1 - X0)
        fy = lambda v: Y1 - (math.log10(v) - math.log10(ylo)) / (math.log10(yhi) - math.log10(ylo)) * (Y1 - Y0)
        med = lambda a: sorted(a)[len(a) // 2]  # giống bản gốc: phần tử giữa (lệch trên khi số chẵn)
        mx, my = med(xs), med(ys)
        amax = max(x["dt28"] for x in mt) or 1
        s = [f'<svg viewBox="0 0 {W} {H}" class="mx" role="img" aria-label="Ma trận cơ hội theo ngách">',
             f'<rect x="{X0}" y="{Y0}" width="{fx(mx) - X0:.1f}" height="{Y1 - Y0}" class="zone"/>',
             f'<text x="{X0 + 8}" y="{Y0 + 16}" class="zl">Mở hơn: top 3 shop nắm ít hơn trung vị</text>']
        v = xlo
        while v <= 1.0001:
            x = fx(v)
            s.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{Y0}" y2="{Y1}" class="gr"/><text x="{x:.1f}" y="{Y1 + 18}" class="ax" text-anchor="middle">{v * 100:.0f}%</text>')
            v += 0.1
        v = ylo
        while v <= yhi * 1.0001:
            y = fy(v)
            s.append(f'<line x1="{X0}" x2="{X1}" y1="{y:.1f}" y2="{y:.1f}" class="gr"/><text x="{X0 - 8}" y="{y + 4:.1f}" class="ax" text-anchor="end">{so(v)}</text>')
            v *= 10
        s.append(f'<line x1="{fx(mx):.1f}" x2="{fx(mx):.1f}" y1="{Y0}" y2="{Y1}" class="med"/><line x1="{X0}" x2="{X1}" y1="{fy(my):.1f}" y2="{fy(my):.1f}" class="med"/>')
        s.append(f'<text x="{(X0 + X1) / 2:.1f}" y="{H - 12}" class="at" text-anchor="middle">Thị phần doanh thu 28 ngày của 3 shop lớn nhất trong ngách</text>')
        s.append(f'<text transform="translate(16 {(Y0 + Y1) / 2:.1f}) rotate(-90)" class="at" text-anchor="middle">Video gắn SP / 1.000 đơn luỹ kế (log)</text>')
        o_da_dat = []  # hộp nhãn đã đặt (x0,y0,x1,y1) + bong bóng
        bong = []
        for x in mt:
            cx, cy = fx(x["top3"]), fy(x["video_1000"])
            r = 6 + 21 * math.sqrt(x["dt28"] / amax)
            bong.append((cx, cy, r, x))
        for cx, cy, r, _ in bong:
            o_da_dat.append((cx - r, cy - r, cx + r, cy + r))
        nhan = []
        for cx, cy, r, x in bong:
            tip = (f'{x["ten"]} · {x["sp"]} SP · {gon(x["dt28"])} doanh thu 28 ngày · top 3 nắm {pct(x["top3"])} · '
                   f'{x["video_1000"]:.0f} video/1.000 đơn luỹ kế')
            s.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" class="b g{x["mau"]}"><title>{e(tip)}</title></circle>')
            w = len(x["ten"]) * 6.6 + 4
            for ax, ay, anchor in [(cx + r + 4, cy + 4, "start"), (cx - r - 4, cy + 4, "end"), (cx, cy - r - 6, "middle"), (cx, cy + r + 14, "middle")]:
                bx0 = ax if anchor == "start" else ax - w if anchor == "end" else ax - w / 2
                hop = (bx0, ay - 12, bx0 + w, ay + 4)
                if hop[0] < X0 or hop[2] > W - 4 or hop[1] < Y0 or hop[3] > Y1:
                    continue
                if any(not (hop[2] < b[0] or hop[0] > b[2] or hop[3] < b[1] or hop[1] > b[3]) for b in o_da_dat):
                    continue
                o_da_dat.append(hop)
                nhan.append(f'<text x="{ax:.1f}" y="{ay:.1f}" class="bl" text-anchor="{anchor}">{e(x["ten"])}</text>')
                break
        s += nhan
        s.append("</svg>")
        return "\n".join(s)

    def bang_ma_tran(self):
        h = ['<div class="tw"><table class="x"><thead><tr><th class="s">Ngách</th><th class="s n">SP</th><th class="s n b">Bán 28 ngày</th>'
             '<th class="s n b">Doanh thu 28 ngày</th><th class="s n">Top 3 nắm</th><th class="s n">Video (FastMoss)</th>'
             '<th class="s n">Video / 1.000 đơn luỹ kế</th><th class="s n">Video tìm được</th><th>3 shop lớn</th></tr></thead><tbody>']
        for x in self.M["ma_tran"]:
            h.append(f'<tr><td>{self.dot(x["nhom"])}{e(x["ten"])}</td>{td_n(x["sp"])}{td_n(x["don28"])}{td_n(x["dt28"], gon(x["dt28"]))}'
                     f'{td_n(x["top3"], pct(x["top3"]))}{td_n(x["video_fm"])}{td_n(x["video_1000"], so(x["video_1000"]))}'
                     f'{td_n(x["video_tim"])}<td>{e(", ".join(x["shop_lon"]))}</td></tr>')
        h.append("</tbody></table></div>")
        return "".join(h)

    # ---- bảng SP dùng chung
    COT_SP = ('<th class="s n">Hạng</th><th class="s">Sản phẩm</th><th class="s">Shop</th><th class="s">{ngach}</th>'
              '<th class="s n" title="Doanh thu 28 ngày chia số đơn 28 ngày">Giá TB</th><th class="s n b">Bán 28 ngày</th>'
              '<th class="s n b">Doanh thu 28 ngày</th><th class="s n">Bán 7 ngày</th><th class="s">7 ngày qua</th>'
              '<th class="s n">Đã bán luỹ kế</th><th class="s n" title="Số video có gắn SP theo FastMoss">Video (FastMoss)</th>'
              '<th class="s n" title="Video gắn SP tìm được trong lượt quét TikTok">Video tìm được</th><th class="s n b">Lượt xem</th>'
              '<th class="s n">KOC tìm được</th><th class="s n">Lên sàn</th>')

    def dong_sp(self, sp, cot_ngach):
        q = N(" ".join([sp["t"], sp.get("sh") or "", sp["ngach"]]))
        cls = ' class="home"' if sp["nha"] == "xac_nhan" else ""
        vid = f'<a href="#d-{e(sp["id"])}">{so(sp["vid_n"])}</a>' if sp["vid_n"] or sp.get("_co_chi_tiet") else so(sp["vid_n"])
        ls = sp["ngay_ls"]
        return (f'<tr{cls} data-q="{e(q)}" data-g="{e(sp["nhom"])}">{td_n(sp["hang"])}<td class="t">{link_sp(sp)}{self.chip_nha(sp)}</td>'
                f'<td>{e(sp.get("sh"))}</td>{cot_ngach}{td_n(round(sp["gia"]), None if sp.get("s28") else "—")}{td_n(sp.get("s28"))}{td_n(sp.get("a28"), gon(sp.get("a28")))}'
                f'{td_n(sp.get("s7"))}{td_xu_huong(sp)}{td_n(sp.get("s"))}{td_n(sp.get("v"))}'
                f'<td class="n" data-v="{sp["vid_n"]}">{vid}</td>{td_n(sp["vid_xem"], gon(sp["vid_xem"]))}{td_n(sp["vid_koc"])}'
                f'<td class="n" data-v="{ls.strftime("%Y%m%d") if ls else 0}">{ngay_ngan(ls)}</td></tr>')

    def chi_tiet(self, sp, mo):
        v = sp["vid_top"]
        k = sp["koc_top"]
        fig = f'{so(sp.get("s28"))} đơn · {so(sp["vid_n"])} video · {gon(sp["vid_xem"])} xem'
        h = [f'<details class="it" id="d-{e(sp["id"])}"{" open" if mo else ""} data-done="1"><summary><span class="rk">{sp["hang"]}</span>'
             f'<span class="nm">{e(sp["t"][:90])} <span class="muted">· {e(sp.get("sh"))}</span></span><span class="fig">{fig}</span></summary><div class="vk">']
        if v:
            h.append(f"<div><h3>Top {len(v)} video gắn SP</h3><ol>")
            h += [f'<li><a href="https://www.tiktok.com/@{e(x[1])}/video/{e(x[0])}" target="_blank" rel="noopener">{e(x[4] or "(không có mô tả)")}</a> '
                  f'<span class="muted">· @{e(x[1])} · {so(x[2])} lượt xem · {e(x[3])}</span></li>' for x in v]
            h.append("</ol></div>")
        else:
            h.append('<div><p class="muted">Chưa tìm thấy video gắn đúng sản phẩm này.</p></div>')
        if k:
            h.append(f"<div><h3>Top {len(k)} KOC theo lượt xem về SP</h3><ol>")
            h += [f'<li><a href="https://www.tiktok.com/@{e(x[0])}" target="_blank" rel="noopener">@{e(x[0])}</a> '
                  f'<span class="muted">· {so(x[1])} lượt xem · {so(x[2])} follower · {x[3]} video</span></li>' for x in k]
            h.append("</ol></div>")
        h.append("</div></details>")
        return "".join(h)

    # ---- Top SP, video & KOC
    def top(self):
        M, b = self.M, self.ch["bang"]
        h = ['<div id="top" class="pane" role="tabpanel" hidden><section><h2>Ma trận cơ hội theo ngách</h2>'
             f'<p class="note">Mỗi bong bóng là một ngách từ {b["ngach_toi_thieu_sp"]} sản phẩm trở lên; kích thước theo doanh thu 28 ngày. '
             'Trục ngang là mức tập trung: càng sang phải, 3 shop lớn càng nắm nhiều. Trục dọc là số video gắn sản phẩm cho mỗi 1.000 đơn: '
             'càng cao, càng phải làm nhiều nội dung mới ra đơn. Đường nét đứt là trung vị, nên vùng xanh chỉ mở hơn khi so với các ngách còn lại.</p>'
             '<div class="legend">']
        h += [f'<span>{self.dot(g["ma"])}{e(g["ten"])}</span>' for g in M["nhom"]]
        h.append(f'</div><div class="mxw" style="margin-top:8px">{self.ma_tran()}</div></section>')
        h.append(f'<section><h3>Số liệu của ma trận</h3>{self.bang_ma_tran()}</section>')
        h.append('<section><h2>Top sản phẩm theo nhóm</h2><div class="subtabs" data-tabs="grp" role="tablist">')
        h += [f'<button data-t="g-{g["ma"]}" role="tab">{e(g["ten"])} · {g["sp"]}</button>' for g in M["nhom"]]
        h.append("</div>")
        for g in M["nhom"]:
            lst = M["theo_nhom"][g["ma"]]
            h.append(f'<div id="g-{g["ma"]}" class="pane" style="padding-top:8px"><div class="tw"><table class="x" id="tb-{g["ma"]}"><thead><tr>'
                     f'{self.COT_SP.format(ngach="Ngách")}</tr></thead><tbody>')
            chi_tiet = [s for s in lst if s["hang"] <= b["chi_tiet_moi_nhom"] or s["nha"] == "xac_nhan"]
            for s in chi_tiet:
                s["_co_chi_tiet"] = True
            for s in lst[:b["top_moi_nhom"]] + [s for s in lst[b["top_moi_nhom"]:] if s["nha"] == "xac_nhan"]:
                h.append(self.dong_sp(s, f'<td class="muted">{e(s["ngach"])}</td>'))
            h.append(f'</tbody></table></div><h3 style="margin-top:14px">Video và KOC của top {b["chi_tiet_moi_nhom"]} và listing nhà</h3>')
            h += [self.chi_tiet(s, s["hang"] <= b["chi_tiet_moi_nhom"]) for s in chi_tiet]
            h.append("</div>")
        h.append("</section></div>")
        return "".join(h)

    def loc_nhom(self, id_bang, id_o, goi_y):
        opt = "".join(f'<option value="{g["ma"]}">{e(g["ten"])}</option>' for g in self.M["nhom"])
        return (f'<div class="filt" data-filter="{id_bang}"><input id="q-{id_o}" type="search" placeholder="{e(goi_y)}" aria-label="{e(goi_y)}">'
                f'<select id="g-{id_o}" aria-label="Lọc nhóm"><option value="">Tất cả nhóm</option>{opt}</select><span class="cnt muted"></span></div>')

    def toan_bo(self):
        M = self.M
        tat_ca = sorted(sum(M["theo_nhom"].values(), []), key=lambda s: -(s.get("s28") or 0))
        h = [f'<div id="all" class="pane" role="tabpanel" hidden><section><h2>Toàn bộ {len(tat_ca)} sản phẩm</h2>'
             '<p class="note">Hạng là thứ hạng trong nhóm theo số đơn 28 ngày. Dòng tô vàng là thương hiệu nhà.</p>',
             self.loc_nhom("tb-all", "all", "Tìm theo tên SP, shop, ngách"),
             f'<div class="tw"><table class="x" id="tb-all"><thead><tr>{self.COT_SP.format(ngach="Nhóm / ngách")}</tr></thead><tbody>']
        h += [self.dong_sp(s, f'<td>{self.dot(s["nhom"])}{e(M["ten_nhom"].get(s["nhom"]))}<br><span class="muted">{e(s["ngach"])}</span></td>')
              for s in tat_ca]
        h.append("</tbody></table></div></section></div>")
        return "".join(h)

    def shop(self):
        M = self.M
        h = [f'<div id="shop" class="pane" role="tabpanel" hidden><section><h2>{len(M["shop"])} shop</h2>'
             '<p class="note">Gộp theo tên shop từ các sản phẩm tìm được, nên số của mỗi shop chỉ gồm những sản phẩm lọt vào lượt quét này. '
             'Nhóm chính là nhóm mang lại nhiều doanh thu nhất cho shop.</p>',
             self.loc_nhom("tb-shop", "shop", "Tìm shop"),
             '<div class="tw"><table class="x" id="tb-shop"><thead><tr><th class="s n">#</th><th class="s">Shop</th><th class="s">Nhóm chính</th>'
             '<th class="s n">SP</th><th class="s n b">Bán 28 ngày</th><th class="s n b">Doanh thu 28 ngày</th><th class="s n">Bán 7 ngày</th>'
             '<th class="s n">Video (FastMoss)</th><th>SP bán chạy nhất</th></tr></thead><tbody>']
        for i, s in enumerate(M["shop"], 1):
            cls = ' class="home"' if s["nha"] == "xac_nhan" else ""
            h.append(f'<tr{cls} data-q="{e(N(s["ten"]))}" data-g="{e(s["nhom"])}">{td_n(i)}<td>{e(s["ten"])}</td>'
                     f'<td>{self.dot(s["nhom"])}{e(M["ten_nhom"].get(s["nhom"]))}</td>{td_n(s["sp"])}{td_n(s["don28"])}'
                     f'{td_n(s["dt28"], gon(s["dt28"]))}{td_n(s["don7"])}{td_n(s["video_fm"])}<td class="t">{link_sp(s["sp_dau"], 70)}</td></tr>')
        h.append("</tbody></table></div></section></div>")
        return "".join(h)

    def nha(self):
        M = self.M
        h = ['<div id="nha" class="pane" role="tabpanel" hidden><section><h2>Thương hiệu nhà trong lượt quét</h2>'
             '<p class="note">Chỉ gồm listing của nhà lọt vào kết quả tìm theo từ khoá, nên chưa phải toàn bộ gian hàng. Số lớn là đơn 28 ngày.</p>']
        if not M["nha"]:
            h.append('<p class="muted">Không có listing nào của thương hiệu nhà trong lượt quét.</p></section></div>')
            return "".join(h)
        h.append('<div class="kpis">')
        h += [f'<div class="kpi"><b>{so(s["don28"])}</b><span>{e(s["ten"])} · {s["listing"]} listing · {gon(s["dt28"])} · {so(s["don7"])} đơn 7 ngày</span></div>'
              for s in M["nha_shop"]]
        h.append('</div></section><section><div class="tw"><table class="x"><thead><tr><th class="s">Nhóm</th><th class="s n">Hạng</th>'
                 '<th class="s">Listing</th><th class="s">Shop</th><th class="s n">Giá TB</th><th class="s n b">Bán 28 ngày</th><th class="s n">Bán 7 ngày</th>'
                 '<th>7 ngày qua</th><th class="s n">Video (FastMoss)</th><th class="s n">KOC (FastMoss)</th><th class="s n">Video tìm được</th>'
                 '<th>So với SP dẫn nhóm</th></tr></thead><tbody>')
        for s in M["nha"]:
            lst = M["theo_nhom"][s["nhom"]]
            dau = lst[0]
            so_voi = "Đang dẫn nhóm" if dau["id"] == s["id"] else f'{e(dau.get("sh"))}: {so(dau.get("s28"))} đơn, giá TB {so(dau["gia"])}'
            vid = f'<a href="#d-{e(s["id"])}">{so(s["vid_n"])}</a>'
            h.append(f'<tr class="home"><td>{self.dot(s["nhom"])}{e(M["ten_nhom"].get(s["nhom"]))}</td>'
                     f'<td class="n" data-v="{s["hang"]}">{s["hang"]}/{len(lst)}</td><td class="t">{link_sp(s, 90)}</td><td>{e(s["sh"])}</td>'
                     f'{td_n(round(s["gia"]), None if s.get("s28") else "—")}{td_n(s.get("s28"))}{td_n(s.get("s7"))}{td_xu_huong(s)}{td_n(s.get("v"))}{td_n(s.get("a"))}'
                     f'<td class="n" data-v="{s["vid_n"]}">{vid}</td><td>{so_voi}</td></tr>')
        h.append("</tbody></table></div></section>")
        vd = M["van_de_nha"]
        if vd:
            h.append('<section><h2>Điểm cần xử lý</h2><ul class="why">')
            for v in vd:
                if v["loai"] == "trung":
                    a, b = v["a"], v["b"]
                    h.append(f'<li><b>Listing trùng giữa hai shop nhà:</b> {link_sp(a, 60)} ({e(a["sh"])}, {so(a.get("s28"))} đơn) và '
                             f'{link_sp(b, 60)} ({e(b["sh"])}, {so(b.get("s28"))} đơn) cùng ngách {e(a["ngach"])}.</li>')
                elif v["loai"] == "khong_don":
                    h.append(f'<li><b>Listing 0 đơn trong 28 ngày:</b> {link_sp(v["a"], 70)} ({e(v["a"]["sh"])}).</li>')
                else:
                    h.append(f'<li><b>Shop có tên giống thương hiệu nhà nhưng chưa xác nhận:</b> {e(v["shop"]["ten"])} '
                             f'({v["shop"]["sp"]} SP, {so(v["shop"]["don28"])} đơn). Hỏi lại để biết là shop nhà, đại lý hay shop khác.</li>')
            h.append("</ul></section>")
        h.append("</div>")
        return "".join(h)

    def video(self):
        M = self.M
        h = ['<div id="vid" class="pane" role="tabpanel" hidden><section>']
        if not M["top_video"]:
            h.append('<h2>Video & KOC</h2><p class="muted">Lượt quét này chưa có dữ liệu video.</p></section></div>')
            return "".join(h)
        h.append(f'<h2>{len(M["top_video"])} video nhiều lượt xem nhất</h2><p class="note">Tính trên video gắn đúng mã của các sản phẩm có chi tiết video. '
                 'Lượt xem là số tích luỹ lúc quét.</p><div class="tw"><table class="x"><thead><tr><th class="s n b">Lượt xem</th><th class="s">Video</th>'
                 '<th class="s">Người đăng</th><th class="s">Ngày đăng</th><th class="s">Sản phẩm gắn</th></tr></thead><tbody>')
        for v, sp in M["top_video"]:
            h.append(f'<tr>{td_n(v[2], gon(v[2]))}<td class="t"><a href="https://www.tiktok.com/@{e(v[1])}/video/{e(v[0])}" target="_blank" rel="noopener">'
                     f'{e(v[4] or "(không có mô tả)")}</a></td><td><a href="https://www.tiktok.com/@{e(v[1])}" target="_blank" rel="noopener">@{e(v[1])}</a></td>'
                     f'<td>{e(v[3])}</td><td class="t">{self.dot(sp["nhom"])}{link_sp(sp, 60)} <span class="muted">· {e(sp.get("sh"))}</span></td></tr>')
        h.append(f'</tbody></table></div></section><section><h2>{len(M["top_koc"])} KOC mang về nhiều lượt xem nhất</h2>'
                 '<p class="note">Cộng lượt xem các video có gắn sản phẩm của từng KOC (chỉ tính KOC lọt top 10 của ít nhất một sản phẩm).</p>'
                 '<div class="tw"><table class="x"><thead><tr><th class="s">KOC</th><th class="s n">Follower</th><th class="s n b">Lượt xem về SP</th>'
                 '<th class="s n">Video</th><th class="s n">Số SP</th><th class="s">Nhóm chính</th></tr></thead><tbody>')
        for k in M["top_koc"]:
            h.append(f'<tr><td><a href="https://www.tiktok.com/@{e(k["u"])}" target="_blank" rel="noopener">@{e(k["u"])}</a></td>'
                     f'{td_n(k["fo"], gon(k["fo"]))}{td_n(k["xem"], gon(k["xem"]))}{td_n(k["video"])}{td_n(k["sp"])}'
                     f'<td>{self.dot(k["nhom"])}{e(M["ten_nhom"].get(k["nhom"]))}</td></tr>')
        h.append("</tbody></table></div></section></div>")
        return "".join(h)

    def cach_lay_so(self):
        tt, k, ch = self.tt, self.M["kpi"], self.ch
        loai = self.luot.get("_loai", [])
        dong = [f'Ngày quét: {e(tt.get("ngay_quet", "?"))}. Số liệu bán hàng tính tới hết {e(tt.get("ngay_chot", "?"))}.']
        fm = "Số đơn 7 và 28 ngày, doanh thu, đã bán luỹ kế, số video và KOC gắn SP: FastMoss, chế độ khách"
        if tt.get("tu_khoa_fastmoss"):
            fm += f', khoảng {tt.get("luot_tim_fastmoss", tt["tu_khoa_fastmoss"])} lượt tìm với {tt["tu_khoa_fastmoss"]} từ khoá'
        dong.append(fm + ". Mỗi lượt chỉ trả 10 SP đầu.")
        truoc_loc = tt.get("sp_truoc_loc") or (k["sp"] + len(loai))
        l = f"Lọc: {so(truoc_loc)} SP → {so(k['sp'])} SP đúng ngành"
        if loai:
            dem = {}
            for x in loai:
                dem[x["ly_do"].split(" (")[0]] = dem.get(x["ly_do"].split(" (")[0], 0) + 1
            l += " (loại " + ", ".join(f"{n} {ly}" for ly, n in sorted(dem.items(), key=lambda x: -x[1])) + ")"
        dong.append(l + ".")
        if self.luot.get("co_video"):
            v = "Video và KOC: tìm video trên tiktok.com (đã đăng nhập)"
            if tt.get("tu_khoa_video"):
                v += f" với {tt['tu_khoa_video']} từ khoá"
            if tt.get("tong_video"):
                v += f"; tổng {so(tt['tong_video'])} video"
            v += f", trong đó {so(k['video_tim'])} video gắn đúng một SP trong báo cáo. Chỉ tính video có gắn mã SP, không tính video chỉ nhắc tên."
            dong.append(v)
            dong.append(f"{k['sp'] - k['sp_co_video']} / {k['sp']} SP chưa tìm thấy video gắn SP trong lượt quét, thường là SP bán qua quảng cáo, "
                        'LIVE hoặc video của chính shop không lên kết quả tìm kiếm. Cột "Video (FastMoss)" là số đầy đủ hơn.')
        else:
            dong.append("Lượt này chưa quét video trên tiktok.com; cột video tìm được để trống, dùng cột Video (FastMoss).")
        if tt.get("ghi_chu"):
            dong.append(e(tt["ghi_chu"]))
        gioi_han = ["Doanh thu là ước tính của FastMoss, không phải doanh thu thật của shop.",
                    '"Đã bán luỹ kế" là số TikTok hiển thị, không có tuổi listing.',
                    "Top 3 shop tính trên doanh thu 28 ngày của các SP tìm được, nên shop có nhiều SP nhỏ lẻ có thể bị tính thấp.",
                    "Ngách chia theo tên SP bằng quy tắc từ khoá (file cấu hình " + e(Path(ch.get("_file", "")).name) + ").",
                    "Không đo được: chi phí quảng cáo, doanh số LIVE tách riêng, tỷ lệ đánh giá 1–3★, lượng tồn kho."]
        return ('<div id="cach" class="pane" role="tabpanel" hidden><section><h2>Cách lấy số</h2>'
                + "".join(f"<p>{x}</p>" for x in dong)
                + '<h3>Giới hạn</h3><ul class="lim">' + "".join(f"<li>{x}</li>" for x in gioi_han) + "</ul></section></div>")

    # ---- cả trang
    def html(self):
        ch = self.ch
        css = (_THU_MUC / "giao_dien.css").read_text(encoding="utf-8")
        gd = ch.get("giao_dien", {})
        for cu, moi in [("--ac:#A12F28", gd.get("nhan")), ("--ac-2:#8A6A1C", gd.get("nha")),
                        ("--ac:#E8746B", gd.get("nhan_dark")), ("--ac-2:#D9B45A", gd.get("nha_dark"))]:
            if moi:
                css = css.replace(cu, cu.split(":")[0] + ":" + moi)
        js = (_THU_MUC / "giao_dien.js").read_text(encoding="utf-8")
        tabs = [("tq", "Tổng quan"), ("top", "Top SP, video & KOC"), ("all", "Toàn bộ sản phẩm"), ("shop", "Shop"),
                ("nha", "Thương hiệu nhà"), ("vid", "Video & KOC")] + [(i, n) for i, n, _ in self.tab_giu] + [("cach", "Cách lấy số")]
        nav = "".join(f'<button data-t="{i}" role="tab">{e(n)}</button>' for i, n in tabs)
        tt = self.tt
        dau = (f'<header class="top"><div><div class="eyebrow">TikTok Shop Việt Nam · 28 ngày tới {e(tt.get("ngay_chot", ""))}</div>'
               f'<h1>{ch["tieu_de_lon"]}</h1></div><div class="meta">Quét ngày {e(tt.get("ngay_quet", ""))} · FastMoss + TikTok · cho {e(ch.get("cho_ai", ""))}</div></header>')
        than = [self.tong_quan(), self.top(), self.toan_bo(), self.shop(), self.nha(), self.video()]
        than += [x for _, _, x in self.tab_giu]
        than.append(self.cach_lay_so())
        return (f'<title>{e(ch["tieu_de_trang"])}</title>\n'
                '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
                '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600&family=Fraunces:ital,opsz,wght@0,9..144,600;1,9..144,600&display=swap">'
                f"<style>\n{css}</style>\n"
                f'<div class="wrap">{dau}<nav class="maintabs" data-tabs="main" role="tablist">{nav}</nav>'
                + "".join(than) + "</div>\n" + "".join(self._json_giu()) + f"<script>\n{js}</script>\n")

    def _json_giu(self):
        return [x for x in getattr(self, "json_giu", [])]


def tach_tab_giu(html_cu, ids):
    """Lấy nguyên các tab (và khối JSON dữ liệu kèm theo) từ trang báo cáo cũ để giữ lại."""
    nav = dict(re.findall(r'<button data-t="([\w-]+)" role="tab">(.*?)</button>', html_cu))
    tabs = []
    for i in ids:
        m = re.search(r'<div id="%s" class="pane"' % re.escape(i), html_cu)
        if not m:
            continue
        n = re.search(r'<(?:main|div) id="[\w-]+" class="pane" role="tabpanel"|</div>\s*<script', html_cu[m.end():])
        tabs.append((i, html.unescape(nav.get(i, i)), html_cu[m.start(): m.end() + (n.start() if n else len(html_cu) - m.end())]))
    json_blocks = re.findall(r'<script type="application/json" id="[\w-]+">.*?</script>', html_cu, re.S)
    return tabs, json_blocks
