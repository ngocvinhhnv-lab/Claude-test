#!/usr/bin/env python3
"""Chuyển tài liệu "Kịch bản video tuần ..." (xuất XML từ Claude Docs) thành file JSON kịch bản cho app.

    python tools/parse_ke_hoach_doc.py doc.xml kich_ban/tuan_2026_10_05.json --batch tuan-2026-10-05

doc.xml là trường data.xml của kết quả đọc tài liệu (hoặc cả file JSON kết quả đọc).
Mỗi kịch bản gồm: tiêu đề cấp 3 "<Mã> · <Góc>", dòng meta "<KÊNH> #<STT> · <Sản phẩm> · Bối cảnh: ... ·
Mở đầu: ... → Chốt: ..." và bảng 4 cột (Mốc, Phần, Lời thoại, Hình ảnh/biểu cảm).
"""

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET

CHANNELS = {"NS": "Newshop", "SH": "Sách Hay", "TV": "Tường Vip", "TL": "Kênh TL"}
QUOTES = "\"“”"
# Chữ trên màn hình nằm trong cột Hình ảnh, dạng: Chữ "44K" / Chữ to "44K" / Phụ đề "..." / Chữ giá "..."
TEXT_RE = re.compile(r"(?:Chữ(?: to| giá)?|Phụ đề|Chữ hiện)\s*[" + QUOTES + r"]([^" + QUOTES + r"]+)[" + QUOTES + r"]")
PLACEHOLDER = re.compile(r"\[[^\]]+\]")
SPEAKER = re.compile(r"(?:^|\s)(Khách|Shop|Chủ shop|Mẹ|Con|Bố)\s*:")


def cell_text(cell):
    return " ".join("".join(t.itertext()).strip() for t in cell.iter("text")).strip()


def para_text(p):
    return "".join("".join(t.itertext()) for t in p.iter("text")).strip()


def parse_range(label):
    m = re.match(r"\s*(\d+(?:[.,]\d+)?)\s*[–-]\s*(\d+(?:[.,]\d+)?)\s*s", label)
    if not m:
        raise ValueError(f"Mốc thời gian lạ: {label!r}")
    a, b = (float(g.replace(",", ".")) for g in m.groups())
    return a, b


def parse_meta(meta):
    parts = [p.strip() for p in meta.split(" · ")]
    channel, stt = re.match(r"([A-Z]+)\s*#(\d+)", parts[0]).groups()
    scene = next((p.split(":", 1)[1].strip() for p in parts if p.startswith("Bối cảnh:")), "")
    hook = next((p for p in parts if p.startswith("Mở đầu:")), "")
    # "Bối cảnh" có thể chứa dấu " · " nên hook/chốt lấy từ phần cuối
    m = re.search(r"Mở đầu:\s*(.+?)\s*→\s*Chốt:\s*(.+)$", meta)
    open_kind, close_kind = (m.group(1), m.group(2)) if m else ("", "")
    product = parts[1] if len(parts) > 1 and not parts[1].startswith(("Bối cảnh", "Mở đầu")) else ""
    return {"channel": channel, "stt": int(stt), "product": product, "scene": scene,
            "open_kind": open_kind.strip(), "close_kind": close_kind.strip(), "hook": hook}


def parse_doc(xml):
    root = ET.fromstring(xml)
    scripts, section, pending = [], "", None
    for el in root:
        if el.tag == "paragraph" and el.get("heading") == "2":
            section = para_text(el)
        elif el.tag == "paragraph" and el.get("heading") == "3":
            m = re.match(r"([A-Z]\d+)\s*·\s*(.+)$", para_text(el))
            pending = {"code": m[1], "angle": m[2], "section": section, "meta": None} if m else None
        elif pending and el.tag == "paragraph" and pending["meta"] is None and para_text(el):
            pending["meta"] = para_text(el)
        elif pending and el.tag == "table":
            rows = [[cell_text(c) for c in r.findall("cell")] for r in el.findall("row")]
            pending["rows"] = [r for r in rows[1:] if len(r) >= 4]
            scripts.append(pending)
            pending = None
    return scripts


def build(raw, batch):
    out = []
    for s in raw:
        meta = parse_meta(s["meta"])
        beats, voice_notes, shot_notes = [], [], []
        for i, (when, part, voice, shot) in enumerate(r[:4] for r in s["rows"]):
            start, end = parse_range(when)
            m = TEXT_RE.search(shot)
            beats.append({"shot": f"{part} · {shot}", "voice": voice, "text": m.group(1) if m else "",
                          "text_pos": "top" if i == 0 else "center" if i == len(s["rows"]) - 1 else "bottom",
                          "duration": round(end - start, 1), "part": part, "when": when})
            voice_notes += PLACEHOLDER.findall(voice) + (PLACEHOLDER.findall(beats[-1]["text"]) if beats[-1]["text"] else [])
            shot_notes += PLACEHOLDER.findall(shot)
        speakers = sorted({m.group(1) for b in beats for m in SPEAKER.finditer(b["voice"])})
        info = []
        if voice_notes:
            info.append("Điền vào lời đọc trước khi dựng (AI sẽ đọc to nếu để nguyên): "
                        + " ".join(dict.fromkeys(voice_notes)))
        if shot_notes:
            info.append("Kiểm tra khi quay: " + " ".join(dict.fromkeys(shot_notes)))
        info.append("Giá trong kịch bản lấy theo giỏ hàng 05/10: so lại với giỏ ngày đăng")
        if len(speakers) > 1:
            info.append("Kịch bản có nhiều người nói (" + ", ".join(speakers) + "): giọng đọc AI chỉ có một giọng, "
                        "nên tự thu âm lời thoại hoặc bỏ nhãn người nói")
        out.append({
            "key": f"{batch}:{s['code']}",
            "origin": "weekly", "status": "ready", "batch": batch,
            "code": s["code"], "channel": meta["channel"], "channel_name": CHANNELS.get(meta["channel"], ""),
            "stt": meta["stt"], "product": meta["product"], "group": s["section"],
            "title": f"{s['code']} · {s['angle']}",
            "summary": f"{CHANNELS.get(meta['channel'], meta['channel'])} #{meta['stt']} · {meta['product']}"
                       f" · Bối cảnh: {meta['scene']}",
            "hook_type": f"Mở đầu: {meta['open_kind']} → Chốt: {meta['close_kind']}",
            "why_it_works": "Kịch bản trong kế hoạch tuần, đã chia sẵn 4 phần: mở đầu, công dụng, thông số, chốt.",
            "beats": beats, "needs_info": info, "caption": "", "hashtags": [],
        })
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source", help="file XML hoặc file JSON kết quả đọc tài liệu")
    p.add_argument("output")
    p.add_argument("--batch", required=True, help="mã đợt, ví dụ tuan-2026-10-05")
    a = p.parse_args()
    raw = open(a.source, encoding="utf-8").read()
    if raw.lstrip().startswith("{"):
        raw = json.loads(raw)["data"]["xml"]
    scripts = build(parse_doc(raw), a.batch)
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump({"batch": a.batch, "scripts": scripts}, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"{len(scripts)} kịch bản, {sum(len(s['beats']) for s in scripts)} cảnh -> {a.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
