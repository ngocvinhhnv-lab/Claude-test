"""Các tác vụ AI dùng Claude API: bóc kịch bản đối thủ, viết lại cho sản phẩm nhà, ghép cảnh."""

import base64
import json
import os

import anthropic

from .store import get_settings

MODEL = "claude-opus-5"

BEAT_SCHEMA = {
    "type": "object",
    "properties": {
        "shot": {"type": "string", "description": "Mô tả cảnh quay: quay gì, góc máy, hành động"},
        "voice": {"type": "string", "description": "Lời thoại/giọng đọc của cảnh, rỗng nếu không có"},
        "text": {"type": "string", "description": "Chữ hiện trên màn hình, rỗng nếu không có"},
        "text_pos": {"type": "string", "enum": ["top", "center", "bottom"]},
        "duration": {"type": "number", "description": "Độ dài cảnh (giây)"},
    },
    "required": ["shot", "voice", "text", "text_pos", "duration"],
    "additionalProperties": False,
}

SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "hook_type": {"type": "string"},
        "why_it_works": {"type": "string"},
        "beats": {"type": "array", "items": BEAT_SCHEMA},
        "caption": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "summary", "hook_type", "why_it_works", "beats", "caption", "hashtags"],
    "additionalProperties": False,
}

REWRITE_SCHEMA = {
    "type": "object",
    "properties": {
        **SCRIPT_SCHEMA["properties"],
        "alt_hooks": {
            "type": "array",
            "description": "Các phương án hook khác cho cảnh đầu",
            "items": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "voice": {"type": "string"}},
                "required": ["text", "voice"],
                "additionalProperties": False,
            },
        },
        "needs_info": {
            "type": "array",
            "description": "Thông tin còn thiếu mà người bán cần bổ sung (giá, khổ, bình luận thật...)",
            "items": {"type": "string"},
        },
    },
    "required": SCRIPT_SCHEMA["required"] + ["alt_hooks", "needs_info"],
    "additionalProperties": False,
}

SYSTEM = (
    "Bạn là chuyên gia nội dung video bán hàng TikTok Shop Việt Nam, làm việc cho một shop tự quay "
    "video sản phẩm. Viết tiếng Việt tự nhiên, ngắn gọn, đúng giọng người bán hàng trên TikTok."
)


class AIError(RuntimeError):
    pass


def is_ready():
    """Đã có Anthropic API key (trong Cài đặt hoặc biến môi trường) chưa."""
    return bool(get_settings().get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY"))


def _client():
    key = get_settings().get("anthropic_api_key") or None
    try:
        return anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
    except anthropic.AnthropicError as err:
        raise AIError("Chưa có Anthropic API key. Nhập key trong mục Cài đặt.") from err


def _image(path):
    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def _ask(content, schema, effort=None, long_output=False):
    """Gọi Claude với đầu ra JSON theo schema, trả về dict. effort: low|medium|high (mặc định high).

    long_output: kết quả có thể rất dài (nhiều kịch bản), dùng streaming và giới hạn đầu ra lớn.
    """
    client = _client()
    kwargs = dict(
        model=MODEL,
        max_tokens=64000 if long_output else 16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        thinking={"type": "adaptive"},
        system=SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": schema},
                       **({"effort": effort} if effort else {})},
        messages=[{"role": "user", "content": content}],
    )
    try:
        if long_output:
            with client.beta.messages.stream(**kwargs) as stream:
                response = stream.get_final_message()
        else:
            response = client.beta.messages.create(**kwargs)
    except anthropic.AuthenticationError as err:
        raise AIError("Anthropic API key không hợp lệ. Kiểm tra lại trong Cài đặt.") from err
    except anthropic.RateLimitError as err:
        raise AIError("Claude API đang giới hạn tần suất, thử lại sau ít phút.") from err
    except anthropic.APIStatusError as err:
        raise AIError(f"Claude API lỗi {err.status_code}: {err.message}") from err
    except anthropic.APIConnectionError as err:
        raise AIError("Không kết nối được Claude API, kiểm tra mạng.") from err
    if response.stop_reason == "refusal":
        raise AIError("Claude từ chối xử lý yêu cầu này.")
    if response.stop_reason == "max_tokens":
        raise AIError("Kết quả quá dài, bị cắt giữa chừng. Thử lại với tài liệu hoặc video ngắn hơn.")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError as err:
        raise AIError("Claude trả về dữ liệu không đọc được.") from err


def transcribe(wav_path):
    """Chuyển giọng nói thành chữ bằng faster-whisper nếu đã cài; trả về None nếu không có."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(wav_path, language="vi")
    return "\n".join(f"[{s.start:.1f}s–{s.end:.1f}s] {s.text.strip()}" for s in segments)


def analyze_competitor(frames, scenes, duration, transcript, notes=""):
    """Bóc kịch bản từ video đối thủ: khung hình theo thời gian + lời thoại (nếu có)."""
    content = [{"type": "text", "text": (
        f"Đây là một video TikTok bán hàng của đối thủ, dài {duration:.1f} giây.\n"
        f"Các mốc chuyển cảnh (giây): {', '.join(f'{t:.1f}' for t in scenes) or 'không phát hiện'}.\n"
        f"Lời thoại tự động (có thể sai chính tả):\n{transcript or '(không có hoặc chưa chuyển thành chữ)'}\n"
        f"Ghi chú của người dùng: {notes or '(không có)'}\n\n"
        "Khung hình theo thời gian:")}]
    for t, path in frames:
        content.append({"type": "text", "text": f"Giây {t:.1f}:"})
        content.append(_image(path))
    content.append({"type": "text", "text": (
        "Hãy bóc tách kịch bản của video này thành các cảnh (beats) theo đúng thứ tự và nhịp cắt thật. "
        "Với mỗi cảnh: mô tả cảnh quay đủ để người khác quay lại được (quay gì, góc máy, hành động), "
        "lời thoại đúng như trong video (sửa lỗi chính tả rõ ràng của bản chuyển chữ), chữ trên màn hình "
        "đọc được từ khung hình và vị trí của nó, độ dài cảnh. Không bịa lời thoại hay chữ không có trong video. "
        "Nêu kiểu hook, tóm tắt, và vì sao video này hiệu quả. Caption và hashtags: đoán theo nội dung "
        "nếu không thấy.")})
    return _ask(content, SCRIPT_SCHEMA)


def rewrite_script(script, product):
    """Giữ cấu trúc kịch bản, viết lại lời và chữ cho sản phẩm của shop."""
    facts = "\n".join(f"- {k}: {v}" for k, v in product.items() if v)
    content = [{"type": "text", "text": (
        "Kịch bản gốc (JSON):\n" + json.dumps(script, ensure_ascii=False, indent=1) + "\n\n"
        "Thông tin sản phẩm của shop:\n" + (facts or "(chưa có)") + "\n\n"
        "Viết lại kịch bản này cho sản phẩm của shop:\n"
        "- Giữ cấu trúc: kiểu hook, số cảnh, nhịp và độ dài từng cảnh, vị trí CTA. Điều chỉnh mô tả cảnh "
        "quay cho phù hợp sản phẩm của shop.\n"
        "- Viết lời thoại mới, không chép nguyên văn đối thủ. Mỗi câu lời thoại đọc vừa độ dài cảnh "
        "(khoảng 4 tiếng mỗi giây). Chữ trên màn hình ngắn, tối đa khoảng 8 từ mỗi dòng.\n"
        "- Chỉ dùng thông tin sản phẩm đã cho. Không bịa giá, khuyến mãi, số liệu, đánh giá hay bình luận "
        "của khách; thiếu thông tin nào thì bỏ qua và liệt kê vào needs_info.\n"
        "- Không hứa công dụng, tài lộc hay sức khoẻ. Cảnh cuối có CTA bấm giỏ hàng.\n"
        "- Đưa thêm 3 phương án hook khác cho cảnh đầu trong alt_hooks.")}]
    return _ask(content, REWRITE_SCHEMA)


def label_shots(items, note=""):
    """Mô tả từng đoạn quay bằng chữ để ghép cảnh về sau không cần gửi lại ảnh.

    items: [(số thứ tự, đường dẫn ảnh giữa đoạn)]. Trả về {số thứ tự: {"desc", "product"}}.
    """
    content = [{"type": "text", "text": (
        "Đây là các đoạn video shop tự quay để bán hàng (tranh, liễn, lịch, thời khóa biểu, trà...). "
        f"Ghi chú của người quay: {note or '(không có)'}.\n"
        "Mỗi đoạn có một ảnh giữa đoạn:")}]
    for index, path in items:
        content.append({"type": "text", "text": f"Đoạn {index}:"})
        content.append(_image(path))
    content.append({"type": "text", "text": (
        "Với mỗi đoạn, viết mô tả ngắn bằng tiếng Việt (tối đa 20 từ) cho biết: có sản phẩm gì (loại, màu, cỡ nếu thấy), "
        "góc máy (toàn cảnh, cận, từ trên xuống), hành động (tay cầm, lật, treo, bóc hộp, máy đang chạy...), "
        "bối cảnh. Chỉ tả điều nhìn thấy, không đoán. Trường product là tên sản phẩm chính nhìn thấy, "
        "để trống nếu không có.\n\n"
        "Ngoài ra cho biết đoạn này có CHỮ CHÁY SẴN hay không, tức chữ do người dựng chèn thêm vào hình: phụ đề lời nói, "
        "chữ chạy, chữ quảng cáo, giá, tên kênh, watermark, sticker chữ. "
        "KHÔNG tính chữ in trên chính sản phẩm (số ngày trên tờ lịch, chữ trên tranh, trên bao bì, trên thời khóa biểu) "
        "và không tính chữ của máy quay (giờ, ngày).\n"
        "- sub: chép lại chữ chèn đó, rỗng nếu không có.\n"
        "- sub_pos: chữ chèn nằm ở phần nào của khung hình (top, center, bottom); 'none' nếu không có.\n"
        "- sub_ok: true nếu đoạn vẫn dùng lại được khi app lồng phụ đề mới (không có chữ chèn, hoặc chữ chèn rất ngắn "
        "và trung tính như tên sản phẩm). false nếu chữ chèn là một câu lời thoại, nhiều dòng, choán phần lớn khung hình, "
        "nói giá hay khuyến mãi, kêu gọi bấm giỏ hàng, hoặc có tên shop/kênh khác — vì phụ đề mới sẽ chồng lên "
        "hoặc nói khác với chữ đang hiện.")})
    schema = {
        "type": "object",
        "properties": {"shots": {"type": "array", "items": {
            "type": "object",
            "properties": {"index": {"type": "integer"}, "desc": {"type": "string"}, "product": {"type": "string"},
                           "sub": {"type": "string"}, "sub_pos": {"type": "string", "enum": ["top", "center", "bottom", "none"]},
                           "sub_ok": {"type": "boolean"}},
            "required": ["index", "desc", "product", "sub", "sub_pos", "sub_ok"], "additionalProperties": False}}},
        "required": ["shots"], "additionalProperties": False,
    }
    result = _ask(content, schema, effort="low")
    return {s["index"]: s for s in result["shots"]}


def _shot_line(shot, used=None):
    """Một dòng mô tả đoạn quay để gửi cho AI: nội dung, độ dài, ghi chú, chữ cháy sẵn, số lần đã dùng."""
    line = f"{shot['id']}: {shot.get('desc') or '(chưa có mô tả, xem ảnh)'} · dài {shot['length']:.0f}s"
    if shot.get("note"):
        line += f" · ghi chú video: {shot['note']}"
    if shot.get("sub"):
        line += f" · trên hình đã có chữ cháy sẵn \"{shot['sub']}\" ở {shot.get('sub_pos') or 'không rõ'}"
    if (used or {}).get(shot["id"]):
        line += f" · đã dùng {used[shot['id']]} lần ở video khác"
    return line


def match_clips(beats, shots, script=None, used=None):
    """Chọn đoạn source phù hợp cho từng cảnh.

    shots: [{id, label, thumb, desc, note, length, scene}]. Đoạn đã có mô tả chữ thì chỉ gửi chữ;
    đoạn chưa có mô tả mới gửi kèm ảnh. used: {id đoạn: số lần đã dùng ở các video trước}.
    """
    script, used = script or {}, used or {}
    content = [{"type": "text", "text": "Kho đoạn video shop đã quay:"}]
    for shot in shots:
        content.append({"type": "text", "text": _shot_line(shot, used)})
        if not shot["desc"]:
            content.append(_image(shot["thumb"]))
    lines = "\n".join(
        f"Cảnh {i} (cần ~{b.get('duration') or 3:.0f}s): {b.get('shot') or '(không mô tả)'} — lời: {b.get('voice') or '-'}"
        for i, b in enumerate(beats))
    content.append({"type": "text", "text": (
        f"Kịch bản: {script.get('title', '')}. Sản phẩm: {script.get('product') or '(không rõ)'}. "
        f"Bối cảnh: {script.get('summary', '')}\n{lines}\n\n"
        "Chọn cho mỗi cảnh một đoạn phù hợp nhất với mô tả cảnh quay, ưu tiên đúng sản phẩm. "
        "Khi nhiều đoạn phù hợp ngang nhau, chọn đoạn ít được dùng hơn để các video không giống nhau, "
        "và không dùng cùng một đoạn cho hai cảnh trong cùng kịch bản nếu còn lựa chọn. "
        "fit: 'tot' nếu đoạn đúng sản phẩm và đúng việc cần quay; 'tam' nếu chỉ dùng tạm được "
        "(đúng sản phẩm nhưng khác góc hoặc hành động); 'khong' nếu kho không có đoạn nào hợp thì chọn 'none'. "
        "Đoạn đã có chữ cháy sẵn trên hình: chỉ chọn khi lời của cảnh không nói khác với chữ đó, và ưu tiên "
        "đoạn không có chữ nếu có lựa chọn ngang nhau. "
        "Mục missing: mô tả cảnh cần quay bổ sung, ngắn gọn, đủ để người khác quay được.")})
    ids = [s["id"] for s in shots] + ["none"]
    schema = {
        "type": "object",
        "properties": {
            "matches": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "beat": {"type": "integer"},
                    "shot_id": {"type": "string", "enum": ids},
                    "fit": {"type": "string", "enum": ["tot", "tam", "khong"]},
                    "reason": {"type": "string"},
                },
                "required": ["beat", "shot_id", "fit", "reason"],
                "additionalProperties": False,
            }},
            "missing": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["matches", "missing"],
        "additionalProperties": False,
    }
    return _ask(content, schema, effort="medium")


def simple_match(beats, shots, used=None):
    """Ghép đơn giản không cần AI: lần lượt chọn đoạn ít được dùng nhất, ưu tiên đoạn kế tiếp trong cùng video.

    Dùng khi chưa có API key hoặc AI lỗi. Không hiểu nội dung nên mọi cảnh đều ở mức 'tam'.
    """
    used, matches, prev = dict(used or {}), [], None
    for i, _ in enumerate(beats):
        def rank(sh):
            follows = 0 if prev and sh["id"] != prev["id"] and sh["source_id"] == prev["source_id"] \
                and sh["start"] >= prev["end"] - 0.01 else 1
            return (used.get(sh["id"], 0), follows, sh["source_id"], sh["start"])
        pick = min(shots, key=rank)
        used[pick["id"]] = used.get(pick["id"], 0) + 1
        prev = pick
        matches.append({"beat": i, "shot_id": pick["id"], "fit": "tam", "reason": "ghép tự động đơn giản"})
    return {"matches": matches, "missing": []}


# ---------- Nhập kịch bản từ tài liệu ----------

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {"scripts": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Mã kịch bản nếu tài liệu có (VD L1, K5), không thì rỗng"},
            "title": {"type": "string"},
            "channel": {"type": "string", "description": "Kênh đăng nếu có (VD NS, TV), không thì rỗng"},
            "product": {"type": "string"},
            "summary": {"type": "string", "description": "Bối cảnh quay hoặc ghi chú ngắn"},
            "hook_type": {"type": "string"},
            "caption": {"type": "string"},
            "hashtags": {"type": "array", "items": {"type": "string"}},
            "beats": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "part": {"type": "string", "description": "Phần của kịch bản (Mở đầu, Công dụng, Thông số, Chốt...), rỗng nếu không có"},
                    "shot": {"type": "string", "description": "Cảnh quay: hình ảnh, biểu cảm, hành động"},
                    "voice": {"type": "string", "description": "Lời thoại nguyên văn"},
                    "text": {"type": "string", "description": "Chữ hiện trên màn hình nếu tài liệu nêu rõ, không thì rỗng"},
                    "duration": {"type": "number", "description": "Độ dài cảnh (giây)"},
                },
                "required": ["part", "shot", "voice", "text", "duration"],
                "additionalProperties": False}},
        },
        "required": ["code", "title", "channel", "product", "summary", "hook_type", "caption", "hashtags", "beats"],
        "additionalProperties": False}}},
    "required": ["scripts"],
    "additionalProperties": False,
}


def extract_scripts(doc):
    """Tách các kịch bản video trong một tài liệu (chữ hoặc PDF) thành danh sách kịch bản có cảnh."""
    content = []
    if doc.kind == "pdf":
        content.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                       "data": base64.standard_b64encode(doc.data).decode("utf-8")}})
        body = ""
    else:
        body = "Nội dung tài liệu (bảng được thể hiện thành các dòng, cột ngăn cách bằng ' | '):\n\n" + doc.text + "\n\n"
    content.append({"type": "text", "text": body + (
        "Tài liệu này chứa các kịch bản video bán hàng của shop (có thể kèm các phần khác như bảng phân bổ, quy tắc chung, "
        "checklist). Hãy trích ra TẤT CẢ kịch bản video, mỗi kịch bản thành các cảnh theo đúng thứ tự.\n"
        "Quy tắc:\n"
        "- Giữ nguyên lời thoại và mô tả cảnh quay trong tài liệu, không tự sáng tác, không rút gọn, không sửa số liệu.\n"
        "- Chữ trong ngoặc vuông như [kiểm tra] là chỗ còn trống: giữ nguyên, tuyệt đối không tự điền.\n"
        "- duration: lấy từ mốc thời gian của cảnh nếu có (VD 3–10s là 7 giây); nếu không có thì ước lượng theo lời thoại, "
        "khoảng 4 từ mỗi giây.\n"
        "- text: chỉ điền chữ hiện trên màn hình khi tài liệu nêu rõ (VD Chữ to \"44K\"), nếu không thì để rỗng.\n"
        "- Không đưa vào kịch bản các phần không phải kịch bản (quy tắc chung, bảng phân bổ, checklist).\n"
        "- Nếu tài liệu không có kịch bản video nào, trả về danh sách rỗng.")})
    return _ask(content, EXTRACT_SCHEMA, effort="medium", long_output=True)["scripts"]


# ---------- Viết lại cảnh cho khớp video đã quay ----------

ADAPT_RULES = (
    "Quy tắc nội dung của shop: xưng 'em', gọi 'anh chị', câu ngắn, văn nói, không đọc như quảng cáo. "
    "Giá, cỡ, số tờ, chất liệu, khuyến mãi chỉ được nói khi đã có trong kịch bản gốc hoặc ghi chú video, "
    "tuyệt đối không bịa thông số, đánh giá, bình luận của khách. Tranh tâm linh hoặc phong thủy: nói 'theo quan niệm', "
    "không hứa tài lộc. Trà: không nói công dụng sức khỏe."
)


def suggest_scripts(shots, count=3, note="", channel="", samples=None):
    """Xem các phân đoạn shop vừa quay rồi viết nhiều kịch bản khác nhau, mỗi cảnh gắn sẵn một đoạn có thật.

    Vì mỗi cảnh phải chọn shot_id trong kho nên lời đọc và hình luôn khớp nhau sau khi dựng.
    """
    content = [{"type": "text", "text": (
        "Đây là tất cả phân đoạn trong video shop vừa quay, liệt kê theo đúng thứ tự quay "
        "(hai đoạn cạnh nhau cùng video là liên tiếp nhau trong thực tế):")}]
    for shot in shots:
        line = _shot_line(shot)
        if shot.get("product"):
            line += f" · sản phẩm: {shot['product']}"
        content.append({"type": "text", "text": line})
    style = "\n".join(f"- {s.get('title', '')} (hook: {s.get('hook_type') or '-'})" for s in (samples or []))
    content.append({"type": "text", "text": (
        f"Thông tin shop cho phép nói (giá, khổ, số tờ, bối cảnh): {note or '(không có)'}\n"
        f"Kênh sẽ đăng: {channel or '(chưa rõ)'}\n"
        + (f"Kịch bản shop đang dùng, để bắt đúng giọng (đừng chép lại):\n{style}\n" if style else "")
        + f"\nHãy phân tích các phân đoạn trên rồi viết {count} kịch bản KHÁC NHAU chỉ dùng chính các đoạn này, "
        "để người bán chọn một cái. Yêu cầu:\n"
        "- Mỗi kịch bản 5–7 cảnh, tổng 20–35 giây. Mỗi cảnh gắn shot_id của một đoạn có thật trong danh sách, "
        "không dùng lại một đoạn hai lần trong cùng kịch bản.\n"
        "- LỜI VÀ HÌNH PHẢI KHỚP: lời của cảnh chỉ được nói về đúng thứ đang thấy trong đoạn đã chọn, hoặc "
        "thông tin shop cho phép nói ở trên. Không nói về cảnh không có trong video.\n"
        "- Mạch phải logic: cảnh đầu là hook từ đoạn bắt mắt nhất, giữa là chi tiết hoặc cách dùng, cảnh cuối chốt "
        "kêu gọi bấm giỏ hàng. Thứ tự các cảnh phải tự nhiên như một video liền mạch, ưu tiên các đoạn liên tiếp "
        "trong cùng video khi chúng kể cùng một việc.\n"
        "- Mỗi kịch bản phải khác nhau thật sự: khác hook, khác góc tiếp cận (hậu trường, cận cảnh chất liệu, "
        "cách dùng, so sánh, lời khuyên), khác thứ tự đoạn.\n"
        "- duration: khoảng số từ của lời chia 4, từ 2 đến 6 giây, không dài hơn đoạn quay quá nhiều.\n"
        "- text: chữ trên màn hình ngắn (tối đa 8 từ) hoặc để rỗng. Đoạn nào đã có chữ cháy sẵn thì để text rỗng, "
        "hoặc đặt text_pos ở vị trí khác chỗ chữ cũ để không chồng chữ.\n"
        "- TUYỆT ĐỐI không dùng ô trống kiểu [kiểm tra]: chỉ viết điều đã biết chắc.\n"
        "- title: tên ngắn nêu rõ hướng tiếp cận của kịch bản đó (tối đa 8 từ). product: sản phẩm chính. "
        "why_it_works: một câu vì sao hướng này hợp với video đang có. caption và hashtag để đăng.\n"
        + ADAPT_RULES)})
    ids = [s["id"] for s in shots]
    beat = {
        "type": "object",
        "properties": {
            "part": {"type": "string", "description": "Vai trò của cảnh: Mở đầu, Chi tiết, Cách dùng, Chốt..."},
            "shot_id": {"type": "string", "enum": ids},
            "voice": {"type": "string"},
            "text": {"type": "string"},
            "text_pos": {"type": "string", "enum": ["top", "center", "bottom"]},
            "duration": {"type": "number"},
        },
        "required": ["part", "shot_id", "voice", "text", "text_pos", "duration"],
        "additionalProperties": False,
    }
    schema = {
        "type": "object",
        "properties": {"scripts": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "title": {"type": "string"}, "product": {"type": "string"}, "summary": {"type": "string"},
                "hook_type": {"type": "string"}, "why_it_works": {"type": "string"},
                "caption": {"type": "string"}, "hashtags": {"type": "array", "items": {"type": "string"}},
                "beats": {"type": "array", "items": beat},
            },
            "required": ["title", "product", "summary", "hook_type", "why_it_works", "caption", "hashtags", "beats"],
            "additionalProperties": False}}},
        "required": ["scripts"], "additionalProperties": False,
    }
    return _ask(content, schema, long_output=True)


def adapt_beats(script, beats, shots, used, fix):
    """Viết lại các cảnh chưa có cảnh quay phù hợp để khớp với video shop đã quay.

    beats: toàn bộ cảnh của kịch bản gốc (để hiểu mạch). fix: {số cảnh: {"shot_id": đoạn tạm hoặc None, "fit": ...}}
    cần chỉnh. shots: kho đoạn quay (đã có mô tả chữ). Trả về {"beats": [...], "suggest_filming": [...]}.
    """
    content = [{"type": "text", "text": "Kho đoạn video shop đã quay:"}]
    by_id = {}
    for shot in shots:
        by_id[shot["id"]] = shot
        content.append({"type": "text", "text": _shot_line(shot, used)})
    lines = []
    for i, beat in enumerate(beats):
        head = f"Cảnh {i} ({beat.get('part') or '-'}, ~{beat.get('duration') or 3:.0f}s)"
        if i in fix:
            cur = by_id.get(fix[i].get("shot_id"))
            lines.append(f"Cảnh {i} CẦN CHỈNH ({beat.get('part') or '-'}, ~{beat.get('duration') or 3:.0f}s). "
                         f"Gốc quay: {beat.get('shot') or '-'} | Lời gốc: {beat.get('voice') or '-'} | "
                         f"Đoạn tạm: {cur['desc'] if cur else 'chưa có đoạn nào hợp'}")
        else:
            lines.append(f"{head} GIỮ NGUYÊN: {beat.get('voice') or '-'}")
    content.append({"type": "text", "text": (
        f"Kịch bản gốc (chỉ để tham khảo ý và mạch): {script.get('title', '')}. Sản phẩm: {script.get('product') or '(không rõ)'}. "
        f"Bối cảnh gốc: {script.get('summary', '')}\n" + "\n".join(lines) + "\n\n"
        "Các cảnh GIỮ NGUYÊN đã có cảnh quay phù hợp, đừng đụng vào. Với mỗi cảnh CẦN CHỈNH, hãy viết lại cảnh đó "
        "dựa trên đoạn quay có sẵn trong kho: chọn đoạn quay phù hợp nhất (shot_id), rồi viết lời thoại và chữ trên màn hình "
        "chỉ nói và chỉ hiện những gì thấy được trong đoạn đó, hoặc thông tin đã có sẵn trong kịch bản gốc và ghi chú video. "
        "Giữ vai trò của cảnh trong mạch (mở đầu, công dụng, thông số, chốt), giữ giọng văn, độ dài lời gần bằng lời gốc "
        "(khoảng 4 từ mỗi giây). Cảnh mở đầu và cảnh chốt kêu gọi bấm giỏ hàng có thể dùng đoạn quay sản phẩm bất kỳ. "
        "Nếu câu gốc có ô [..] chưa điền mà vẫn dùng ý đó, giữ nguyên ô [..], không tự điền. "
        "Nếu kho không có đoạn nào liên quan đến sản phẩm này và không thể nói trung thực điều gì cho cảnh đó thì đặt usable=false. "
        "Ưu tiên đoạn ít được dùng ở video khác. " + ADAPT_RULES + "\n"
        "suggest_filming: tối đa 3 gợi ý cảnh nên quay thêm để video lần sau tốt hơn (không bắt buộc), ngắn gọn.")})
    ids = list(by_id) + ["none"]
    schema = {
        "type": "object",
        "properties": {
            "beats": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "beat": {"type": "integer"},
                    "usable": {"type": "boolean"},
                    "shot_id": {"type": "string", "enum": ids},
                    "voice": {"type": "string"},
                    "text": {"type": "string"},
                    "text_pos": {"type": "string", "enum": ["top", "center", "bottom"]},
                    "reason": {"type": "string", "description": "Đã đổi gì và vì sao, một câu"},
                },
                "required": ["beat", "usable", "shot_id", "voice", "text", "text_pos", "reason"],
                "additionalProperties": False}},
            "suggest_filming": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["beats", "suggest_filming"],
        "additionalProperties": False,
    }
    return _ask(content, schema, effort="medium")
