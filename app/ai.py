"""Các tác vụ AI dùng Claude API: bóc kịch bản đối thủ, viết lại cho sản phẩm nhà, ghép cảnh."""

import base64
import json

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


def _ask(content, schema, effort=None):
    """Gọi Claude với đầu ra JSON theo schema, trả về dict. effort: low|medium|high (mặc định high)."""
    client = _client()
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            thinking={"type": "adaptive"},
            system=SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": schema},
                           **({"effort": effort} if effort else {})},
            messages=[{"role": "user", "content": content}],
        )
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
        raise AIError("Kết quả quá dài, bị cắt giữa chừng. Thử lại với video ngắn hơn.")
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
        "để trống nếu không có.")})
    schema = {
        "type": "object",
        "properties": {"shots": {"type": "array", "items": {
            "type": "object",
            "properties": {"index": {"type": "integer"}, "desc": {"type": "string"}, "product": {"type": "string"}},
            "required": ["index", "desc", "product"], "additionalProperties": False}}},
        "required": ["shots"], "additionalProperties": False,
    }
    result = _ask(content, schema, effort="low")
    return {s["index"]: s for s in result["shots"]}


def match_clips(beats, shots, script=None, used=None):
    """Chọn đoạn source phù hợp cho từng cảnh.

    shots: [{id, label, thumb, desc, note, length, scene}]. Đoạn đã có mô tả chữ thì chỉ gửi chữ;
    đoạn chưa có mô tả mới gửi kèm ảnh. used: {id đoạn: số lần đã dùng ở các video trước}.
    """
    script, used = script or {}, used or {}
    content = [{"type": "text", "text": "Kho đoạn video shop đã quay:"}]
    for shot in shots:
        line = f"{shot['id']}: {shot['desc'] or '(chưa có mô tả, xem ảnh)'} · dài {shot['length']:.0f}s"
        if shot.get("note"):
            line += f" · ghi chú video: {shot['note']}"
        if used.get(shot["id"]):
            line += f" · đã dùng {used[shot['id']]} lần ở video khác"
        content.append({"type": "text", "text": line})
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
