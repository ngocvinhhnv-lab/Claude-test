#!/usr/bin/env python3
"""Tạo nhiều video từ 1 video gốc bằng ffmpeg.

Hai cách dùng:

1. Theo file cấu hình (kiểm soát từng video):
       python make_videos.py config.json

2. Tự động chia (nhanh, không cần cấu hình):
       python make_videos.py goc.mp4 --every 15 --ratio 9:16
       python make_videos.py goc.mp4 --scenes --min 8 --max 30 --ratio 9:16,1:1

Xem README.md để biết đầy đủ các tuỳ chọn.
"""

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

RATIOS = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
    "16:9": (1920, 1080),
}

DEFAULTS = {
    "ratio": "9:16",       # một tỉ lệ hoặc danh sách, "original" = giữ nguyên
    "fit": "blur",         # blur | crop | pad
    "speed": 1.0,
    "fps": 30,
    "fade": 0.0,           # giây fade in/out, 0 = tắt
    "text": None,          # chữ hiện suốt video
    "text_pos": "top",     # top | center | bottom
    "captions": [],        # [{"start": 0, "end": 3, "text": "..."}]
    "logo": None,
    "logo_pos": "top-right",
    "logo_size": 0.18,     # tỉ lệ so với cạnh ngắn của video
    "music": None,
    "music_volume": 0.3,
    "keep_audio": True,    # giữ tiếng gốc khi chèn nhạc
    "audio_volume": 1.0,   # âm lượng tiếng gốc
    "voice": None,         # file giọng đọc, đặt từ giây 0 của video
    "voice_volume": 1.0,
    "duck": True,          # tự hạ nhạc khi có giọng đọc
    "safe_zone": False,    # tránh vùng TikTok che (thanh tab, cột nút, caption)
    # Arial có sẵn trên Windows/macOS và đủ dấu tiếng Việt; Linux thường có DejaVu Sans
    "font": "Arial" if sys.platform in ("win32", "darwin") else "DejaVu Sans",
    "crf": 20,
}


def find_ffmpeg():
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("Không tìm thấy ffmpeg. Cài ffmpeg hoặc chạy: pip install imageio-ffmpeg")


FFMPEG = find_ffmpeg()

TONEMAP = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
           "tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p")


def parse_time(value):
    """Nhận 12, "12.5", "1:05", "01:02:03.5" -> số giây."""
    if isinstance(value, (int, float)):
        return float(value)
    parts = str(value).strip().split(":")
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    return seconds


def fmt_time(seconds):
    m, s = divmod(seconds, 60)
    return f"{int(m):02d}:{s:05.2f}"


def probe(path):
    """Lấy thời lượng, kích thước và việc có âm thanh hay không."""
    out = subprocess.run([FFMPEG, "-hide_banner", "-i", path],
                         capture_output=True, text=True).stderr
    dur = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    size = re.search(r"Video: .*?(\d{2,5})x(\d{2,5})", out)
    if not dur and not size:
        sys.exit(f"Không đọc được file: {path}\n{out}")
    if size and re.search(r"rotation of -?90", out):
        size = (None, size[2], size[1])  # video quay dọc: ffmpeg tự xoay khi xuất
    return {
        "duration": int(dur[1]) * 3600 + int(dur[2]) * 60 + float(dur[3]) if dur else 0.0,
        "width": int(size[1]) if size else None,
        "height": int(size[2]) if size else None,
        "has_audio": "Audio:" in out,
        # Video HDR của iPhone (HLG) hoặc HDR10 cần chuyển về SDR, nếu không sẽ bạc màu
        "hdr": bool(re.search(r"arib-std-b67|smpte2084", out)),
    }


def parse_clip(clip, duration):
    """Clip dạng ["0:05", "0:20"], "0:05-0:20" hoặc {"start":..,"end":..}."""
    if isinstance(clip, str):
        start, end = clip.split("-", 1)
    elif isinstance(clip, dict):
        start, end = clip.get("start", 0), clip.get("end", duration)
    else:
        start, end = clip
    start = max(0.0, parse_time(start))
    end = duration if end in (None, "end", "") else min(duration, parse_time(end))
    if end <= start:
        raise ValueError(f"Đoạn cắt không hợp lệ: {clip}")
    return start, end


def atempo_chain(speed):
    """atempo chỉ nhận 0.5–2.0, nên xâu chuỗi cho tốc độ ngoài khoảng đó."""
    filters = []
    while speed > 2.0:
        filters.append("atempo=2.0")
        speed /= 2.0
    while speed < 0.5:
        filters.append("atempo=0.5")
        speed /= 0.5
    filters.append(f"atempo={speed:.4f}")
    return ",".join(filters)


def frame_filter(ratio, fit, src_w, src_h, tag=""):
    """Filter đưa video về khung hình đích. Trả về (filter, W, H).

    tag: hậu tố cho nhãn nội bộ, cần khi dùng nhiều lần trong cùng một filtergraph.
    """
    if ratio == "original":
        w, h = (src_w or 1920) // 2 * 2, (src_h or 1080) // 2 * 2
        return f"scale={w}:{h},setsar=1", w, h
    if ratio not in RATIOS:
        raise ValueError(f"Tỉ lệ không hỗ trợ: {ratio} (dùng {', '.join(RATIOS)} hoặc original)")
    w, h = RATIOS[ratio]
    if fit == "crop":
        f = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"
    elif fit == "pad":
        f = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
             f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1")
    elif fit == "blur":
        f = (f"split=2[bg{tag}][fg{tag}];"
             f"[bg{tag}]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
             f"boxblur=25:5[bg2{tag}];"
             f"[fg{tag}]scale={w}:{h}:force_original_aspect_ratio=decrease[fg2{tag}];"
             f"[bg2{tag}][fg2{tag}]overlay=(W-w)/2:(H-h)/2,setsar=1")
    else:
        raise ValueError(f"fit không hợp lệ: {fit} (blur | crop | pad)")
    return f, w, h


def ass_escape(text):
    return str(text).replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def ass_time(seconds):
    h, rem = divmod(max(0.0, seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def build_ass(opts, w, h, total, path, top_min=0):
    """Viết file phụ đề ASS cho chữ tiêu đề và caption theo thời gian.

    top_min: khoảng cách tối thiểu từ mép trên (để chữ không đè logo).
    Với khung dọc và safe_zone bật, chữ tránh các vùng TikTok che: thanh tab
    phía trên, cột nút bên phải và phần tên kênh/caption phía dưới.
    """
    align = {"top": 8, "center": 5, "bottom": 2}
    base = min(w, h)  # tính theo cạnh ngắn để chữ đều nhau ở mọi khung hình
    size = round(base / 14)
    margin_v = round(base * 0.08)
    ml = mr = round(base * 0.06)
    bottom_v = round(h * 0.15)
    if opts.get("safe_zone") and h > w:
        margin_v = max(margin_v, round(h * 0.09))
        mr = round(w * 0.15)
        bottom_v = round(h * 0.22)
    if opts["text_pos"] == "top":
        margin_v = max(margin_v, top_min)
    # BorderStyle=3: nền hộp mờ sau chữ; BorderStyle=1: chữ trắng viền đen kiểu phụ đề TikTok
    style = ("Style: {name},{font},{size},{color},&H00FFFFFF,&H{outline},&H80000000,"
             "-1,0,0,0,100,100,0,0,{border},{pad},0,{align},{ml},{mr},{mv},1")
    common = dict(font=opts["font"], ml=ml, mr=mr, color="&H00FFFFFF")
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}",
        "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        style.format(name="Title", size=size, pad=round(size * 0.25), border=3, outline="80000000",
                     align=align.get(opts["text_pos"], 8), mv=margin_v, **common),
        style.format(name="Caption", size=round(size * 0.9), pad=round(size * 0.2), border=3,
                     outline="80000000", align=2, mv=bottom_v, **common),
        style.format(name="CapTop", size=size, pad=round(size * 0.25), border=3,
                     outline="80000000", align=8, mv=margin_v, **common),
        style.format(name="CapCenter", size=round(size * 1.1), pad=round(size * 0.25), border=3,
                     outline="80000000", align=5, mv=0, **common),
        style.format(name="Sub", size=round(size * 0.95), pad=max(3, round(size * 0.09)),
                     border=1, outline="00000000", align=2, mv=bottom_v, **common),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    if opts.get("text"):
        lines.append(f"Dialogue: 0,{ass_time(0)},{ass_time(total)},Title,,0,0,0,,"
                     f"{ass_escape(opts['text'])}")
    styles = {"bottom": "Caption", "top": "CapTop", "center": "CapCenter", "sub": "Sub"}
    for cap in opts.get("captions") or []:
        start = parse_time(cap.get("start", 0))
        end = parse_time(cap.get("end", total))
        style_name = styles.get(cap.get("pos", "bottom"), "Caption")
        lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},{style_name},,0,0,0,,"
                     f"{ass_escape(cap['text'])}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def filter_path(path):
    """Escape đường dẫn để dùng bên trong filtergraph."""
    return path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


_PROBE_CACHE = {}


def probe_cached(path):
    key = (path, os.path.getmtime(path))
    if key not in _PROBE_CACHE:
        _PROBE_CACHE[key] = probe(path)
    return _PROBE_CACHE[key]


def clip_segments(source, info, clips):
    """Chuẩn hoá danh sách clip thành (nguồn, info, start, end, tốc độ, giây giữ khung cuối).

    Clip dạng dict có thể chỉ định "source" (video khác), "speed" và "pad".
    """
    segs = []
    for clip in clips:
        opt = clip if isinstance(clip, dict) else {}
        src = opt.get("source") or source
        sinfo = info if src == source and info else probe_cached(src)
        start, end = parse_clip(clip, sinfo["duration"])
        segs.append((src, sinfo, start, end, float(opt.get("speed", 1.0)), float(opt.get("pad", 0.0))))
    return segs


def render(source, info, opts, ratio, out_path, tmpdir):
    segs = clip_segments(source, info, opts["clips"])
    speed = float(opts["speed"])
    seg_lens = [(e - s) / sp + pad for _, _, s, e, sp, pad in segs]
    total = sum(seg_lens) / speed
    fade = float(opts["fade"] or 0)

    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y"]
    # Mỗi đoạn là một input riêng với -ss để tua nhanh, không phải giải mã từ đầu
    for src, _, s, e, _, _ in segs:
        cmd += ["-ss", f"{s:.3f}", "-t", f"{e - s:.3f}", "-i", src]
    next_input = len(segs)
    logo_idx = music_idx = voice_idx = None
    if opts.get("logo"):
        cmd += ["-i", opts["logo"]]
        logo_idx, next_input = next_input, next_input + 1
    if opts.get("music"):
        cmd += ["-stream_loop", "-1", "-i", opts["music"]]
        music_idx, next_input = next_input, next_input + 1
    if opts.get("voice"):
        cmd += ["-i", opts["voice"]]
        voice_idx = next_input

    use_src_audio = (any(si["has_audio"] for _, si, *_ in segs)
                     and (opts["keep_audio"] or music_idx is None)
                     and float(opts["audio_volume"]) > 0)
    first = segs[0][1]
    _, w, h = frame_filter(ratio, opts["fit"], first["width"], first["height"])
    graph = []
    for i, (_, sinfo, s, e, sp, pad) in enumerate(segs):
        # Đưa từng đoạn về cùng khung hình trước khi nối, vì các nguồn có thể khác kích thước
        ff, _, _ = frame_filter(ratio, opts["fit"], first["width"], first["height"], tag=str(i))
        vf = f"[{i}:v]{TONEMAP + ',' if sinfo['hdr'] else ''}setpts=(PTS-STARTPTS)/{sp},fps={opts['fps']}"
        if pad > 0:
            vf += f",tpad=stop_mode=clone:stop_duration={pad:.3f}"
        graph.append(f"{vf},{ff},format=yuv420p,trim=duration={seg_lens[i]:.3f}[v{i}]")
        if use_src_audio:
            if sinfo["has_audio"]:
                af = f"[{i}:a:0]asetpts=PTS-STARTPTS,aresample=44100,aformat=channel_layouts=stereo"
                if sp != 1.0:
                    af += "," + atempo_chain(sp)
                af += f",volume={opts['audio_volume']}"
            else:
                af = "aevalsrc=0:c=stereo:s=44100"
            graph.append(f"{af},apad,atrim=0:{seg_lens[i]:.3f}[a{i}]")
    n = len(segs)
    if use_src_audio:
        pairs = "".join(f"[v{i}][a{i}]" for i in range(n))
        graph.append(f"{pairs}concat=n={n}:v=1:a=1[vc][ac]")
    else:
        pairs = "".join(f"[v{i}]" for i in range(n))
        graph.append(f"{pairs}concat=n={n}:v=1:a=0[vc]")

    v, a = "[vc]", "[ac]" if use_src_audio else None
    if speed != 1.0:
        graph.append(f"{v}setpts=PTS/{speed}[vs]")
        v = "[vs]"
        if a:
            graph.append(f"{a}{atempo_chain(speed)}[as]")
            a = "[as]"

    top_min = 0
    if logo_idx is not None:
        lw = round(min(w, h) * float(opts["logo_size"]))
        m = round(min(w, h) * 0.04)
        logo = probe(opts["logo"])
        if opts["logo_pos"].startswith("top") and logo["width"]:
            top_min = m + round(lw * logo["height"] / logo["width"]) + m // 2
        pos = {
            "top-right": f"W-w-{m}:{m}", "top-left": f"{m}:{m}",
            "bottom-right": f"W-w-{m}:H-h-{m}", "bottom-left": f"{m}:H-h-{m}",
        }[opts["logo_pos"]]
        graph.append(f"[{logo_idx}:v]scale={lw}:-1,format=rgba[lg]")
        graph.append(f"{v}[lg]overlay={pos}[vl]")
        v = "[vl]"

    if opts.get("text") or opts.get("captions"):
        ass = os.path.join(tmpdir, os.path.basename(out_path) + ".ass")
        build_ass(opts, w, h, total, ass, top_min)
        graph.append(f"{v}ass='{filter_path(ass)}'[vt]")
        v = "[vt]"

    if fade > 0:
        graph.append(f"{v}fade=t=in:st=0:d={fade},fade=t=out:st={max(0, total - fade):.3f}:d={fade}[vfd]")
        v = "[vfd]"

    mix = [a] if a else []
    if voice_idx is not None:
        graph.append(f"[{voice_idx}:a]volume={opts['voice_volume']},aresample=44100,"
                     f"aformat=channel_layouts=stereo,apad,atrim=0:{total:.3f},"
                     f"asetpts=PTS-STARTPTS,asplit=2[vo][vosc]")
    if music_idx is not None:
        graph.append(f"[{music_idx}:a]volume={opts['music_volume']},aresample=44100,"
                     f"aformat=channel_layouts=stereo,atrim=0:{total:.3f},asetpts=PTS-STARTPTS[mu]")
        mu = "[mu]"
        if voice_idx is not None and opts.get("duck", True):
            # Tự hạ nhạc khi có giọng đọc, nhạc lớn lại khi giọng dừng
            graph.append("[mu][vosc]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=400[mud]")
            mu = "[mud]"
        elif voice_idx is not None:
            graph.append("[vosc]anullsink")
        mix.append(mu)
    elif voice_idx is not None:
        graph.append("[vosc]anullsink")
    if voice_idx is not None:
        mix.append("[vo]")
    if len(mix) > 1:
        graph.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:dropout_transition=0:normalize=0[amx]")
        a = "[amx]"
    elif mix:
        a = mix[0]
    if a:
        graph.append(f"{a}alimiter=limit=0.95[alim]")  # tránh vỡ tiếng khi trộn
        a = "[alim]"
    if a and fade > 0:
        graph.append(f"{a}afade=t=in:st=0:d={fade},afade=t=out:st={max(0, total - fade):.3f}:d={fade}[afd]")
        a = "[afd]"

    cmd += ["-filter_complex", ";".join(graph), "-map", v]
    if a:
        cmd += ["-map", a, "-c:a", "aac", "-b:a", "128k"]
    else:
        cmd += ["-an"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(opts["crf"]),
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-t", f"{total:.3f}", out_path]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg lỗi")
    return total


def detect_scenes(source, threshold):
    """Trả về danh sách mốc chuyển cảnh (giây)."""
    cmd = [FFMPEG, "-hide_banner", "-i", source, "-an",
           "-vf", f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"]
    out = subprocess.run(cmd, capture_output=True, text=True).stderr
    return [float(t) for t in re.findall(r"pts_time:([\d.]+)", out)]


def auto_clips(info, args):
    duration = info["duration"]
    if args.every:
        step = args.every
        cuts = [i * step for i in range(int(duration // step) + 1)] + [duration]
    else:
        cuts = [0.0] + detect_scenes(args.source, args.threshold) + [duration]
    cuts = sorted(set(round(c, 3) for c in cuts))

    clips, start = [], cuts[0]
    for t in cuts[1:]:
        if t - start < args.min and t != duration:
            continue  # cảnh quá ngắn -> gộp với cảnh sau
        if t - start < args.min and clips:
            start, _ = clips.pop()  # đoạn cuối quá ngắn -> gộp vào đoạn trước
        # Đoạn dài hơn --max thì chia đều thành nhiều phần
        parts = max(1, math.ceil((t - start) / args.max))
        piece = (t - start) / parts
        clips += [(start + k * piece, start + (k + 1) * piece) for k in range(parts)]
        start = t
    return clips


def build_jobs_from_args(args):
    info = probe(args.source)
    clips = auto_clips(info, args)
    base = os.path.splitext(os.path.basename(args.source))[0]
    shared = {k: v for k, v in {
        "ratio": args.ratio.split(","), "fit": args.fit, "speed": args.speed,
        "fade": args.fade, "text": args.text, "text_pos": args.text_pos,
        "logo": args.logo, "logo_pos": args.logo_pos, "music": args.music,
        "music_volume": args.music_volume, "keep_audio": not args.mute,
    }.items() if v is not None}
    return {
        "source": args.source,
        "output_dir": args.out,
        "defaults": shared,
        "videos": [
            {"name": f"{base}_{i:02d}", "clips": [[fmt_time(s), fmt_time(e)]]}
            for i, (s, e) in enumerate(clips, 1)
        ],
    }


def apply_beats(opts, duration):
    """Dựng video theo từng cảnh của kịch bản.

    Mỗi cảnh: {"clip": ["0:05", "0:08"], "text": chữ trên màn hình,
    "pos": vị trí chữ (top | center | bottom), "sub": lời thoại hiện ở dưới,
    "canh": mô tả cảnh (chỉ để ghi chú)}. Thời gian chữ tự tính theo cảnh.
    """
    clips, captions, t = [], list(opts.get("captions") or []), 0.0
    for beat in opts["beats"]:
        if not beat.get("clip"):
            sys.exit(f"{opts.get('name', 'video')}: cảnh \"{beat.get('canh', '?')}\" "
                     f"chưa có mốc thời gian (clip)")
        start, end = parse_clip(beat["clip"], duration)
        length = (end - start) / float(opts["speed"])
        clips.append([start, end])
        if beat.get("text"):
            captions.append({"start": t, "end": t + length, "text": beat["text"],
                             "pos": beat.get("pos", "top")})
        if beat.get("sub"):
            captions.append({"start": t, "end": t + length, "text": beat["sub"], "pos": "bottom"})
        t += length
    opts["clips"], opts["captions"] = clips, captions


def run(config, base_dir, dry_run=False):
    source = os.path.join(base_dir, config["source"])
    out_dir = os.path.join(base_dir, config.get("output_dir", "output"))
    info = probe(source)
    print(f"Video gốc: {config['source']} — {fmt_time(info['duration'])}, "
          f"{info['width']}x{info['height']}, {'có' if info['has_audio'] else 'không có'} âm thanh")

    shared = {**DEFAULTS, **config.get("defaults", {})}
    jobs = []
    for idx, video in enumerate(config["videos"], 1):
        opts = {**shared, **video}
        for key in ("logo", "music", "voice"):
            if opts.get(key):
                opts[key] = os.path.join(base_dir, opts[key])
        if opts.get("beats"):
            apply_beats(opts, info["duration"])
        opts.setdefault("clips", [[0, "end"]])
        ratios = opts["ratio"] if isinstance(opts["ratio"], list) else [opts["ratio"]]
        name = opts.get("name", f"video_{idx:02d}")
        for ratio in ratios:
            suffix = "" if len(ratios) == 1 else "_" + ratio.replace(":", "x")
            jobs.append((opts, ratio, os.path.join(out_dir, f"{name}{suffix}.mp4")))

    print(f"Sẽ tạo {len(jobs)} video vào {out_dir}/")
    if dry_run:
        for opts, ratio, path in jobs:
            clips = ", ".join(f"{fmt_time(s)}-{fmt_time(e)}"
                              for s, e in (parse_clip(c, info["duration"]) for c in opts["clips"]))
            print(f"  {os.path.basename(path)}  [{ratio}]  {clips}")
        return

    os.makedirs(out_dir, exist_ok=True)
    failed = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, (opts, ratio, path) in enumerate(jobs, 1):
            label = f"[{i}/{len(jobs)}] {os.path.basename(path)}"
            try:
                total = render(source, info, opts, ratio, path, tmpdir)
                print(f"{label}  ✓ {fmt_time(total)}")
            except (RuntimeError, ValueError) as err:
                failed += 1
                print(f"{label}  ✗ {err}")
    if failed:
        sys.exit(f"{failed} video lỗi")


def main():
    p = argparse.ArgumentParser(description="Tạo nhiều video từ 1 video gốc.")
    p.add_argument("source", help="file cấu hình .json hoặc video gốc (chế độ tự động)")
    p.add_argument("--dry-run", action="store_true", help="chỉ in kế hoạch, không xuất video")
    p.add_argument("--print-config", action="store_true",
                   help="in file cấu hình tương ứng để chỉnh tay rồi chạy lại")
    auto = p.add_argument_group("chế độ tự động (khi đưa vào video)")
    auto.add_argument("--every", type=float, help="cắt mỗi N giây")
    auto.add_argument("--scenes", action="store_true", help="cắt theo chuyển cảnh")
    auto.add_argument("--threshold", type=float, default=0.3, help="độ nhạy chuyển cảnh (0–1)")
    auto.add_argument("--min", type=float, default=5, help="độ dài tối thiểu mỗi video (giây)")
    auto.add_argument("--max", type=float, default=60, help="độ dài tối đa mỗi video (giây)")
    auto.add_argument("--out", default="output")
    auto.add_argument("--ratio", default="9:16", help="vd: 9:16 hoặc 9:16,1:1,16:9")
    auto.add_argument("--fit", choices=["blur", "crop", "pad"])
    auto.add_argument("--speed", type=float)
    auto.add_argument("--fade", type=float)
    auto.add_argument("--text")
    auto.add_argument("--text-pos", choices=["top", "center", "bottom"])
    auto.add_argument("--logo")
    auto.add_argument("--logo-pos", choices=["top-right", "top-left", "bottom-right", "bottom-left"])
    auto.add_argument("--music")
    auto.add_argument("--music-volume", type=float)
    auto.add_argument("--mute", action="store_true", default=None, help="bỏ tiếng gốc khi chèn nhạc")
    args = p.parse_args()

    if args.source.lower().endswith(".json"):
        with open(args.source, encoding="utf-8") as f:
            config = json.load(f)
        base_dir = os.path.dirname(os.path.abspath(args.source))
    else:
        if not (args.every or args.scenes):
            p.error("với video gốc, cần chọn --every N hoặc --scenes (hoặc dùng file .json)")
        config = build_jobs_from_args(args)
        base_dir = os.getcwd()

    if args.print_config:
        print(json.dumps(config, ensure_ascii=False, indent=2))
        return
    run(config, base_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
